#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build an offline HTML report from preserved experiment outputs, never from invented scores."""
import argparse
from collections import Counter
import datetime
import hashlib
import html
import json
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def live_skill_drift():
    drift = []
    for frozen in sorted((ROOT / 'frozen/skills').glob('*/SKILL.md')):
        expected = hashlib.sha256(frozen.read_bytes()).hexdigest()
        for label, base in [('repository', REPO / 'skills'),
                            ('claude', Path.home() / '.claude/skills'),
                            ('codex', Path.home() / '.agents/skills')]:
            path = base / frozen.parent.name / 'SKILL.md'
            actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
            if actual != expected:
                drift.append({'location': label, 'skill': frozen.parent.name,
                              'expected_sha256': expected, 'actual_sha256': actual})
    return drift


def summarize(run):
    frozen = ROOT / 'frozen'
    cases = read(frozen / 'evals/java-kotlin-suite/cases.json')
    rubrics = {r['id']: r for r in read(frozen / 'evals/java-kotlin-suite/rubrics.json')}
    root = ROOT / 'runs' / run
    labels = read(root / 'judge-label-key.json', {})
    manual = read(root / 'manual-audit.json', {'checked': [], 'overrides': [], 'note': 'Не выполнено'})
    overrides = {(x['id'], x['arm']): x for x in manual['overrides']}
    rows = []
    for case in cases:
        row = {**case, 'rubric': rubrics[case['id']], 'arms': {}}
        judge_folder = root / 'judges' / case['id']
        judge_result = read(judge_folder / 'result.json')
        judgments = read(judge_folder / 'answer.json', {}).get('judgments', [])
        if not judge_result or judge_result['status'] != 'completed':
            judgments = []
        valid_labels = Counter(j.get('label') for j in judgments) == Counter({'X': 1, 'Y': 1})
        for arm in ['A', 'B']:
            folder = root / 'trials' / (case['id'] + '-' + arm)
            result = read(folder / 'result.json')
            answer = read(folder / 'answer.json')
            raw = (folder / 'answer.txt').read_text() if (folder / 'answer.txt').exists() else ''
            grade = next((j for j in judgments if labels.get(case['id'], {}).get(j.get('label')) == arm), None) if valid_labels else None
            if grade:
                if (len(grade['must_met']) != len(row['rubric']['must']) or
                        len(grade['must_not_violated']) != len(row['rubric']['must_not'])):
                    grade = None
            entry = {'result': result, 'answer': answer, 'raw_answer': raw, 'judge': grade,
                     'pass': None, 'evidence_path': str(folder.relative_to(ROOT))}
            if grade and result and result['status'] == 'completed':
                entry['pass'] = (all(grade['must_met']) and not any(grade['must_not_violated']) and
                                 not grade['false_positive'] and not grade['harmful_advice'])
            if (case['id'], arm) in overrides:
                entry['override'] = overrides[(case['id'], arm)]
                entry['pass'] = entry['override']['pass']
            row['arms'][arm] = entry
        rows.append(row)
    metrics = {}
    for arm in ['A', 'B']:
        entries = [r['arms'][arm] for r in rows]
        completed = [e for e in entries if e['result'] and e['result']['status'] == 'completed']
        graded = [e for e in entries if e['pass'] is not None]
        usage = Counter()
        for e in completed:
            usage.update(e['result'].get('usage') or {})
        metrics[arm] = {
            'attempted': sum(e['result'] is not None for e in entries),
            'completed': len(completed), 'graded': len(graded),
            'passed': sum(e['pass'] for e in graded),
            'verdict_matches': sum((r['arms'][arm]['answer'] or {}).get('verdict') ==
                                   ('issue' if r['rubric']['group'] == 'problem' else 'ok')
                                   for r in rows if r['arms'][arm]['result'] and
                                   r['arms'][arm]['result']['status'] == 'completed'),
            'input_tokens': usage['input_tokens'], 'cached_input_tokens': usage['cached_input_tokens'],
            'cache_creation_input_tokens': usage['cache_creation_input_tokens'],
            'output_tokens': usage['output_tokens'],
            'reasoning_output_tokens': usage['reasoning_output_tokens'],
            'mean_seconds': round(statistics.mean(e['result']['seconds'] for e in completed), 2) if completed else None,
            'median_seconds': round(statistics.median(e['result']['seconds'] for e in completed), 2) if completed else None,
            'answer_chars': sum(e['result']['answer_chars'] for e in completed),
            'problem_passed': sum(r['arms'][arm]['pass'] is True for r in rows if r['rubric']['group'] == 'problem'),
            'correct_passed': sum(r['arms'][arm]['pass'] is True for r in rows if r['rubric']['group'] == 'correct'),
            'false_positives': sum(bool(e.get('override', e.get('judge') or {}).get('false_positive')) for e in graded),
            'harmful_advice': sum(bool(e.get('override', e.get('judge') or {}).get('harmful_advice')) for e in graded),
            'tool_events': sum((e['result'] or {}).get('tool_events', 0) for e in entries),
            'structured_output_events': sum((e['result'] or {}).get('structured_output_events', 0) for e in entries),
        }
    pairs = Counter()
    for r in rows:
        a, b = r['arms']['A']['pass'], r['arms']['B']['pass']
        pairs['ungraded' if a is None or b is None else
              'both_pass' if a and b else 'A_only' if a else 'B_only' if b else 'both_fail'] += 1
    judge_usage = Counter()
    judge_results = [read(p) for p in sorted((root / 'judges').glob('*/result.json'))]
    for r in judge_results:
        judge_usage.update(r.get('usage') or {})
    base_topics = {'naming', 'solid', 'contracts', 'domain-modeling', 'refactoring', 'errors',
                   'nullability', 'collections', 'generics', 'concurrency', 'resources', 'rest-api',
                   'validation', 'serialization', 'persistence', 'sql-migrations', 'testing',
                   'security', 'time', 'observability'}
    skills = []
    for path in sorted((frozen / 'skills').glob('*/SKILL.md')):
        content = path.read_text()
        title = re.search(r'^# (.+)$', content, re.M).group(1)
        topic = path.parent.name.removeprefix('java-kotlin-')
        urls = list(dict.fromkeys(re.findall(r'https?://[^\s)<>]+', content)))
        skills.append({'name': path.parent.name, 'topic': topic, 'title': title, 'content': content,
                       'base': topic in base_topics, 'chars': len(content),
                       'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'urls': urls})
    probes = {p.stem: read(p) for p in (ROOT / 'probes').glob('*.json')}
    config = read(root / 'run.json', {})
    model_ids = sorted({model for row in rows for entry in row['arms'].values()
                        for model in (entry.get('result') or {}).get('model_usage', {})})
    engine = config.get('engine')
    if engine == 'claude':
        label = 'Claude / ' + (', '.join(model_ids) or config.get('model', '?'))
        model_note = 'Model ID из modelUsage: ' + (', '.join(model_ids) or 'пока не получен') + '. Идентификатор не гарантирует неизменяемую серверную реализацию.'
        cost_note = 'Вход Claude = input_tokens + cache_read_input_tokens + cache_creation_input_tokens. Cached - чтение кэша; создание показано отдельно. Thinking входит в output. CLI возвращает оценку по прайс-листу, не счет по подписке; фактическая денежная стоимость неизвестна.'
    elif engine == 'codex':
        label = 'Codex / ' + config.get('model', '?')
        model_note = 'CLI сообщает gpt-6.1-sol, но предупреждает об отсутствии model metadata и использует fallback metadata. Неизменяемый серверный snapshot не раскрыт.'
        cost_note = 'Токены - данные Codex CLI; cached входит в input, reasoning входит в output. Денежная стоимость неизвестна: использована авторизация ChatGPT, а не отчет о тарификации API.'
    else:
        raise ValueError('Unsupported or missing engine: ' + str(engine))
    return {'generated_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'run': run, 'run_config': read(root / 'run.json'), 'metrics': metrics, 'pairs': dict(pairs),
            'display': {'label': label + ' / ' + config.get('effort', '?'),
                        'model_note': model_note, 'cost_note': cost_note},
            'observed_model_ids': model_ids,
            'rows': rows, 'skills': skills, 'manual_audit': manual, 'probes': probes,
            'judge_completed': sum(r['status'] == 'completed' for r in judge_results),
            'judge_usage': dict(judge_usage), 'manifest': read(frozen / 'manifest.json'),
            'protocol': (ROOT / 'PROTOCOL.md').read_text(),
            'analysis_notes': (root / 'ANALYSIS_NOTES.md').read_text() if (root / 'ANALYSIS_NOTES.md').exists() else (ROOT / 'ANALYSIS_NOTES.md').read_text() if engine == 'codex' else 'Анализ Claude еще не завершен.',
            'claude_protocol': (ROOT / 'CLAUDE_PROTOCOL.md').read_text() if engine == 'claude' else '',
            'audit_response': (ROOT / 'AUDIT_RESPONSE.md').read_text() if (ROOT / 'AUDIT_RESPONSE.md').exists() else '',
            'live_skill_drift': live_skill_drift(),
            'selection': (REPO / 'SKILL_SELECTION.md').read_text()}


def preflight_summary():
    paths = [ROOT / 'probes' / name / 'result.json' for name in
             ['claude-authenticated-probe', 'claude-explicit-isolation-probe', 'claude-structured-output-probe']]
    for run in ['claude-opus55-max', 'claude-opus55-isolated-max']:
        paths.extend(sorted((ROOT / 'runs' / run / 'trials').glob('*/result.json')))
    rows = []
    for path in paths:
        if not path.exists():
            continue
        result = read(path)
        raw = result.get('raw_usage', result.get('usage') or {})
        usage = result.get('usage') or {}
        input_tokens = usage['input_tokens'] if 'raw_usage' in result else sum(raw.get(k, 0) for k in
            ['input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'])
        rows.append({'path': str(path.relative_to(ROOT)), 'status': result['status'],
                     'input_tokens': input_tokens, 'output_tokens': usage.get('output_tokens', 0),
                     'list_cost_usd': result.get('reported_list_cost_usd', result.get('cost_usd'))})
    return {'rows': rows, 'input_tokens': sum(r['input_tokens'] for r in rows),
            'output_tokens': sum(r['output_tokens'] for r in rows),
            'list_cost_usd': sum(r['list_cost_usd'] or 0 for r in rows),
            'actual_cost_usd': None}


TEMPLATE = r'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><title>Java / Kotlin — навыки и A/B-бенчмарк</title>
<style>
:root{--bg:#f4f5f1;--panel:#fff;--ink:#192821;--muted:#56675c;--line:#dce3da;--green:#176745;--wash:#edf6ef;--amber:#875216;--red:#ab3f38;--code:#eff2ec}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:var(--green);text-underline-offset:3px}button,input,select{font:inherit}button,select{cursor:pointer}header,main,footer{max-width:1220px;margin:auto;padding:30px 38px}header{padding-top:55px;padding-bottom:12px}.eyebrow{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--green);font-weight:750}.topline{display:flex;justify-content:space-between;gap:20px;align-items:center}h1{font-size:clamp(34px,5vw,62px);line-height:1.08;letter-spacing:-.045em;font-weight:730;max-width:920px;margin:25px 0}h2{font-size:28px;line-height:1.25;margin:0 0 16px;letter-spacing:-.02em}h3{font-size:19px;margin:0 0 10px}p{margin:0 0 15px}.lead{font-size:21px;max-width:910px;color:var(--muted)}.muted,small{color:var(--muted)}nav{display:flex;gap:10px;flex-wrap:wrap;margin:26px 0 4px}nav a{text-decoration:none;padding:6px 12px;border:1px solid var(--line);border-radius:30px;font-size:14px;background:var(--panel)}section{margin:0 0 40px}.notice{border-left:4px solid var(--amber);background:var(--panel);border-radius:6px;padding:20px 24px;margin-bottom:25px}.notice strong{color:var(--amber)}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:24px}.value{font-size:42px;line-height:1.2;letter-spacing:-.05em;font-weight:750;margin:8px 0}.label{font-size:14px;color:var(--muted)}.pill{display:inline-block;border-radius:20px;padding:2px 10px;font-size:12px;font-weight:650;background:var(--wash);color:var(--green)}.pill.warn{color:var(--amber);background:var(--code)}.pill.bad{color:var(--red);background:var(--code)}.two{display:grid;grid-template-columns:1fr 1fr;gap:20px}.box{padding:26px;border:1px solid var(--line);border-radius:14px;background:var(--panel)}ul,ol{padding-left:22px}li{margin:7px 0}.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--panel)}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:12px 15px;border-bottom:1px solid var(--line);vertical-align:top}th{background:var(--wash);font-weight:650}tr:last-child td{border:0}.toolbar{display:flex;gap:12px;flex-wrap:wrap;margin:15px 0}.toolbar input{flex:1;min-width:200px}input,select,button{border:1px solid var(--line);background:var(--panel);color:var(--ink);padding:9px 13px;border-radius:8px}button:hover{border-color:var(--green)}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid var(--green);outline-offset:3px}details{border:1px solid var(--line);background:var(--panel);border-radius:10px;margin:10px 0}summary{padding:15px 19px;cursor:pointer;font-weight:600}details[open]>summary{border-bottom:1px solid var(--line)}.inside{padding:20px}.response{padding:18px;background:var(--bg);border-radius:10px;min-width:0}.response h4{margin:0 0 12px}.response p{font-size:14px}.finding{border-left:3px solid var(--amber);padding-left:12px;margin-bottom:16px}.finding b{font-size:14px}.judge{font-size:13px;border-top:1px solid var(--line);padding-top:12px;margin-top:15px}pre,code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px}pre{padding:16px;background:var(--code);border-radius:8px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.6;margin:12px 0}code{overflow-wrap:anywhere}.skill-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 16px}.skill-grid details{align-self:start}.skill-grid summary{font-size:15px}.source-list{font-size:12px;overflow-wrap:anywhere}.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:14px;margin:16px 0}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--green);margin-right:5px}.dot.bad{background:var(--red)}.bar{height:12px;display:flex;border-radius:6px;overflow:hidden;background:var(--line);margin:20px 0}.bar span{min-width:0}.subtle{font-size:13px}.resultline{padding:24px;background:var(--wash);border-radius:14px;margin:22px 0;font-size:18px}.count{font-size:13px;color:var(--muted);margin-bottom:15px}.status-ok{color:var(--green);font-weight:650}.status-fail{color:var(--red);font-weight:650}.status-na{color:var(--muted)}footer{border-top:1px solid var(--line);font-size:13px;padding-bottom:50px}.empty{padding:30px;color:var(--muted)}.hidden{display:none!important}
@media(prefers-color-scheme:dark){:root{--bg:#121a17;--panel:#1a2620;--ink:#e4ede5;--muted:#a0b4a5;--line:#304338;--green:#8dd7ad;--wash:#203b2c;--amber:#e5b574;--red:#f2a5a0;--code:#223127}}
@media(max-width:800px){header,main,footer{padding-left:20px;padding-right:20px}.cards{grid-template-columns:repeat(2,1fr)}.two,.skill-grid{grid-template-columns:1fr}.topline{align-items:flex-start}.lead{font-size:18px}.card{padding:18px}.value{font-size:34px}}
@media print{body{background:white;color:black}nav,.toolbar,button{display:none}.box,.card,details{break-inside:avoid}header,main,footer{max-width:none;padding:15px}details:not([open]) .inside{display:none}a{color:black}}
</style></head><body>
<header><div class="topline"><span class="eyebrow">Личный комплект · Java / Kotlin / Spring</span><span class="pill" id="date"></span></div>
<h1>30 навыков.<br>Проверка пользы на коде.</h1><p class="lead">Парное сравнение коротких ревью: одна и та же задача без нового навыка и с одним профильным SKILL.md. Полные ответы и критерии — ниже.</p>
<nav><a href="#results">Результат</a><a href="#method">Как проверяли</a><a href="#cases">Все задачи</a><a href="#skills">30 навыков</a><a href="#next">Что делать утром</a><a href="#proof">Доказательства</a></nav></header>
<main>
<div class="notice"><strong>Две отдельные серии: Codex и Claude Opus.</strong> Сравнение со скиллом и без проводится внутри каждой серии. Разные модели, effort и оценщики не позволяют считать таблицу рейтингом моделей. Первые диагностические пробы Claude исключены и сохранены отдельно.</div>
<details><summary>Диагностические пробы Claude, исключенные из результатов</summary><div class="inside" id="preflights"></div></details>
<section id="series"><h2>Выберите серию</h2><div class="toolbar"><select id="series-select" aria-label="Серия бенчмарка"></select></div><div id="series-overview" class="table-wrap"></div><p class="subtle">Полная рубрика чувствительна к полноте ответа. Столбец issue/ok отражает только основной вердикт, а не точность каждого совета.</p></section>
<section id="results"><h2 id="series-title">Что получилось</h2><div class="cards" id="metrics"></div><div class="resultline" id="verdict"></div><p>Оценка строгая: пропуск одного пункта авторской рубрики даёт «не прошёл», даже когда главный вывод верен. Разница в этом показателе не равна числу дополнительно найденных багов. Отдельно ниже показано совпадение основного вердикта issue/ok.</p><p class="muted" id="efficiency"></p>
<div class="two"><div class="box"><h3>Парные исходы</h3><div id="pair-chart"></div><div id="pair-rows"></div><p class="subtle muted">Сравнение по содержанию: выполнены обязательные критерии, нет запрещённых советов, ложных обязательных исправлений и вредных рекомендаций.</p></div>
<div class="box"><h3>Контекст и время</h3><div id="cost"></div><p class="subtle muted" id="cost-note"></p></div></div>
</section>
<section id="method"><h2>Как читать этот результат</h2><div class="two"><div class="box"><h3>Контролируемые условия</h3><ul>
<li>60 заданий: 30 с дефектом и 30 корректных. В каждой из 30 тем — оба типа.</li><li>Свежий процесс и пустая рабочая папка для каждого ответа. Одна модель, effort и формат ответа в A и B.</li><li>В B добавлен полный текст одного замороженного навыка. В A его нет. Порядок 120 запусков перемешан заранее.</li><li>Скрыты rubric, название навыка в A, метки «дефектный/корректный» и предыдущие ответы. Автопоиск skills, plugins, memory, hooks, web, apps и shell отключены флагами.</li><li>Модель-оценщик получает rubric и ответы с перемешанными метками X/Y. Ключ групп скрыт; объяснения сохранены.</li></ul></div>
<div class="box"><h3>Границы вывода</h3><ul>
<li>Задачи были открыты при разработке навыков. Это учебная проверка, не независимый holdout.</li><li>Один ответ на условие; повторяемость и польза на большом проекте не установлены.</li><li>Проверено ревью фрагментов. Генерация и выполнение нового кода моделью не проверялись.</li><li>Навык добавлен в контекст явно. Автоматический выбор навыка и загрузка через Claude Code не тестировались.</li><li>Испытуемая и модель-оценщик имеют одно клиентское имя. Повторную проверку делает автор отчёта — ИИ-ассистент; независимой человеческой оценки нет. Стиль ответа может косвенно раскрывать группу.</li><li id="model-note"></li></ul></div></div>
<details><summary>Полный протокол, зафиксированный до результатов</summary><div class="inside"><pre id="protocol"></pre><pre id="claude-protocol"></pre></div></details><details><summary>Как отличали неполный ответ от пропущенного дефекта</summary><div class="inside"><pre id="analysis-notes"></pre></div></details></section>
<section id="cases"><h2>60 задач, два ответа на каждую</h2><p class="muted">«Прошёл» — итог по рубрике, а не просто совпадение verdict. Откройте задачу: внутри контекст, код, оба ответа и основания оценки.</p>
<div class="toolbar"><input id="search" type="search" aria-label="Поиск задачи" placeholder="Название темы или текст задачи"><select id="filter" aria-label="Фильтр задач"><option value="all">Все задачи</option><option value="different">Различается итог A/B</option><option value="failed">Есть провал</option><option value="problem">Фрагменты с дефектом</option><option value="correct">Корректные фрагменты</option></select><button id="expand">Раскрыть видимые</button></div><div class="count" id="case-count"></div><div id="case-list"></div></section>
<section id="skills"><h2>Комплект: 20 базовых + 10 по ситуации</h2><div class="notice"><strong>Аудит выявил замечания к исходному снимку.</strong> Подтверждены неверная Kotlin-форма assertThrowsExactly и недостаточно явные границы транзакций в SQL-примере; нужны уточнения naming, observability и версий JVM. Бенчмарк относится к замороженному снимку до исправлений. Текущие файлы могли измениться в другой сессии; расхождения перечислены ниже. Успех на учебных задачах не проверяет каждый пример.</div><details><summary>Проверка внешнего аудита: подтверждения и возражения</summary><div class="inside"><p id="live-drift"></p><pre id="audit-response"></pre></div></details><p class="muted">Каждый навык — один файл, с примерами и конкретными источниками. Полный текст встроен в этот HTML. «Базовый» не означает загрузку всех 20 в каждую задачу.</p>
<div class="toolbar"><select id="skill-filter" aria-label="Фильтр навыков"><option value="all">Все 30</option><option value="base">20 базовых</option><option value="optional">10 по ситуации</option></select></div><div class="skill-grid" id="skill-list"></div>
<details><summary>План отбора, шесть возможных слияний и границы тем</summary><div class="inside"><pre id="selection"></pre></div></details></section>
<section id="next"><h2>С чего начать утром</h2><div class="box"><ol>
<li>Для первого рабочего ревью выберите <code>/java-kotlin-naming</code>; для изменения ролей и зависимостей — <code>/java-kotlin-solid</code>. Исходники и установленные копии всех 30 навыков подготовлены.</li>
<li>Вызывайте профильный навык по задаче. Начните с 20 базовых; оставьте ситуационные для соответствующего стека. Не удаляйте навык только из-за одного учебного A/B-сценария.</li>
<li>Результаты Opus и Codex выбираются выше. Для осознанного повторного эксперимента используйте новое имя серии; старые ответы не перезаписывайте. Команда ниже служит примером.</li>
<li>Следующий более сильный эксперимент: отложенная выборка реальных open-source изменений, несколько повторов и слепая человеческая оценка. Измеряйте также создание кода с исполнением тестов. Это рекомендация, не уже выполненная проверка.</li></ol>
<pre>python3 evals/java-kotlin-benchmark/run_benchmark.py run \
  --engine claude --model claude-opus-5-5 --effort max --run opus-new \
  --workers 2

# После успешных ответов — отдельно оценка сохранённых пар:
python3 evals/java-kotlin-benchmark/run_benchmark.py judge \
  --engine claude --model claude-opus-5-5 --effort max --run opus-new --workers 2</pre>
<p class="subtle muted">Команды выполняются из корня java_kotlin_harness. <code>opus</code> — алиас; runner сохраняет modelUsage, если CLI его вернёт. Для конкретной версии укажите доступный точный ID. Сетевой маршрут при необходимости задаётся параметром <code>--proxy</code>; глобальные настройки не меняются.</p></div></section>
<section id="proof"><h2>Проверяемые основания</h2><div class="two"><div class="box"><h3>Файлы и данные</h3><p id="audit-note"></p><p id="run-note"></p><div class="toolbar"><button id="download">Скачать все данные JSON</button></div><ul>
<li><a href="PROTOCOL.md">Протокол</a> · <a href="frozen/manifest.json">SHA-256 снимка</a></li><li><a href="run_benchmark.py">Runner</a> · <a href="build_report.py">Генератор отчёта</a></li><li><a href="probes/claude-auth-probe.json">Неудачная проба Claude</a> · <a href="probes/codex-proxy-probe.json">Успешная проба Codex</a></li><li><a href="../../SKILL_SELECTION.md">План отбора навыков</a> · <a href="../java-kotlin-suite/EVALUATION.md">Отдельные локальные проверки</a></li></ul>
<p class="subtle muted">Ответы, rubric, frozen skills и оценки встроены в HTML; отчёт работает без сети. Ссылки на файлы рядом дают дополнительные журналы, когда открыт оригинал из репозитория.</p></div>
<div class="box"><h3>Другое доказательство, отдельно от A/B</h3><p>До этого эксперимента пройдены 30 исполняемых проверок контрактов библиотек: 16 Java, 12 Kotlin и 2 ожидаемых отказа компиляции. Это проверки примеров и API; они не оценивают качество ответа LLM.</p><p>Структура и ссылки проверялись отдельно; совпадение текущих исходников и установок со снимком указано в разделе навыков. Полного Spring/PostgreSQL интеграционного прогона нет.</p><p class="subtle">Методические источники: <a href="https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices">Anthropic: skill evaluation</a>, <a href="https://developers.openai.com/api/docs/guides/evaluation-best-practices">OpenAI: eval best practices</a>, <a href="https://developers.openai.com/codex/cli/reference/">Codex CLI reference</a>. Размер корпуса и критерий pass — авторские решения. Технические источники каждого навыка перечислены внутри него.</p></div></div></section>
</main><footer><p>Локальный отчёт · Без публикации, commit или push. Снимок навыков после начала серии не подстраивался под ответы. Создан <span id="timestamp"></span>.</p></footer>
<script id="data" type="application/json">__DATA__</script>
<script>
'use strict';
const REPORT=JSON.parse(document.getElementById('data').textContent);
const SERIES=REPORT.series;
let D=SERIES[SERIES.length-1];
const el=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=n=>Number(n).toLocaleString('ru-RU');
const grade=v=>v===true?'<span class="status-ok">Прошёл</span>':v===false?'<span class="status-fail">Не прошёл</span>':'<span class="status-na">Не оценён</span>';
function renderSeries(){
el('series-title').textContent=D.display.label;
el('model-note').textContent=D.display.model_note;
el('cost-note').textContent=D.display.cost_note+' Время включает сеть и запуск CLI, по '+D.run_config.workers+' процесса одновременно.';
el('claude-protocol').textContent=D.claude_protocol;
el('audit-response').textContent=D.audit_response;
el('live-drift').textContent=D.live_skill_drift.length?'Текущие файлы отличаются от проверенного снимка: '+D.live_skill_drift.map(x=>x.location+'/'+x.skill).join(', ')+'. Эти версии данным прогоном не проверялись.':'Текущие исходники и установленные файлы совпадают с проверенным снимком.';
el('date').textContent=new Date(D.generated_utc).toLocaleDateString('ru-RU',{timeZone:'Europe/Moscow'});
el('timestamp').textContent=new Date(D.generated_utc).toLocaleString('ru-RU',{timeZone:'Europe/Moscow'})+' МСК';
const A=D.metrics.A,B=D.metrics.B,paired=60-(D.pairs.ungraded||0),delta=B.passed-A.passed;
el('metrics').innerHTML=[['Без навыка',`${A.passed} / ${A.graded}`,'ревью прошли критерии'],['С одним навыком',`${B.passed} / ${B.graded}`,'ревью прошли критерии'],['Изменение',`${delta>0?'+':''}${delta}`,'успешных сценариев'],['Реальные ответы',num(A.completed+B.completed),'из 120 запланированных']].map(([l,v,s])=>`<div class="card"><div class="label">${l}</div><div class="value">${v}</div><small>${s}</small></div>`).join('');
el('efficiency').textContent=A.completed===60&&B.completed===60?`С навыком суммарный входящий контекст изменился на ${((B.input_tokens/A.input_tokens-1)*100).toFixed(1)}%. Это измеренная цена дополнительной инструкции; сама по себе длина контекста не означает улучшение качества.`:'';
el('verdict').textContent=paired<60?'Серия ещё не полностью оценена. Итоговые выводы делать рано.':
 delta===0?'На этом наборе итоговый pass-rate одинаков. Превосходство навыков по этому показателю не обнаружено; это не доказательство их бесполезности.':
 delta>0?`Разница в числе пройденных сценариев на этом учебном наборе: +${delta}. Это предварительный результат одной серии; устойчивость по повторам и перенос на реальные проекты не проверены.`:
 `На этом учебном наборе с навыками пройдено на ${-delta} сценариев меньше. Провалы нужно разобрать до вывода о пользе; данные не подтверждают безусловное улучшение.`;
const pairs=[['Оба варианта прошли','both_pass','var(--green)'],['Прошёл только с навыком','B_only','#65a77b'],['Прошёл только без навыка','A_only','var(--amber)'],['Оба не прошли','both_fail','var(--red)'],['Пара не оценена','ungraded','var(--line)']];
el('pair-chart').innerHTML='<div class="bar" aria-label="Распределение исходов пар">'+pairs.map(([l,k,c])=>`<span style="width:${(D.pairs[k]||0)/60*100}%;background:${c}" title="${l}: ${D.pairs[k]||0}"></span>`).join('')+'</div>';
el('pair-rows').innerHTML='<table><tbody>'+pairs.map(([l,k])=>`<tr><td>${l}</td><td><b>${D.pairs[k]||0}</b></td></tr>`).join('')+'</tbody></table>';
el('cost').innerHTML='<table><thead><tr><th>Показатель</th><th>Без навыка</th><th>С навыком</th></tr></thead><tbody>'+[
['Совпал вердикт issue/ok',A.verdict_matches+' / 60',B.verdict_matches+' / 60'],['Проблемные: прошли всю рубрику',A.problem_passed+' / 30',B.problem_passed+' / 30'],['Корректные: прошли всю рубрику',A.correct_passed+' / 30',B.correct_passed+' / 30'],['Ложные замечания',A.false_positives,B.false_positives],['Вредные советы',A.harmful_advice,B.harmful_advice],['Input tokens',num(A.input_tokens),num(B.input_tokens)],['Cached input',num(A.cached_input_tokens),num(B.cached_input_tokens)],['Cache creation input (Claude)',num(A.cache_creation_input_tokens),num(B.cache_creation_input_tokens)],['Output tokens',num(A.output_tokens),num(B.output_tokens)],['Из них reasoning/thinking',num(A.reasoning_output_tokens),num(B.reasoning_output_tokens)],['Медиана ответа, сек.',A.median_seconds,B.median_seconds]].map(r=>'<tr>'+r.map((v,i)=>`<${i?'td':'td'}>${esc(v)}</td>`).join('')+'</tr>').join('')+'</tbody></table>';
el('protocol').textContent=D.protocol;el('selection').textContent=D.selection;el('analysis-notes').textContent=D.analysis_notes;
function response(e,arm){let a=e.answer,j=e.judge,body='';if(a){body=(a.findings||[]).map(f=>`<div class="finding"><b>${esc(f.problem)}</b><p>${esc(f.evidence)}</p><p><b>Предложение:</b> ${esc(f.fix)}</p></div>`).join('')+`<p>${esc(a.summary)}</p>`}else{body=`<pre>${esc(e.raw_answer||'Ответ ещё не получен')}</pre>`}let evaluation=j?`<div class="judge"><b>Оценщик:</b> ${esc(j.reason)}<br><b>Цитата:</b> ${esc(j.evidence)}<br>must: ${j.must_met.map(x=>x?'✓':'✗').join(' · ')}; нарушений must_not: ${j.must_not_violated.filter(Boolean).length}.</div>`:'';if(e.override)evaluation+=`<div class="judge"><b>Поправка автора:</b> ${esc(e.override.reason)}</div>`;return `<div class="response"><h4>${arm==='A'?'A · Без навыка':'B · С навыком'} — ${grade(e.pass)}</h4>${body}${evaluation}<details><summary>Сырой ответ и метаданные</summary><div class="inside"><pre>${esc(e.raw_answer)}</pre><pre>${esc(JSON.stringify(e.result,null,2))}</pre><a href="${esc(e.evidence_path)}/stdout.txt">JSONL CLI</a></div></details></div>`}
function renderCases(){const q=el('search').value.toLowerCase(),filter=el('filter').value;const rows=D.rows.filter(r=>{let a=r.arms.A.pass,b=r.arms.B.pass;return JSON.stringify([r.id,r.context,r.files]).toLowerCase().includes(q)&&(filter==='all'||filter==='different'&&a!==null&&b!==null&&a!==b||filter==='failed'&&(a===false||b===false)||filter===r.rubric.group)});el('case-count').textContent=`Показано ${rows.length} из ${D.rows.length}`;el('case-list').innerHTML=rows.map(r=>`<details class="case"><summary>${esc(r.id)} <span class="pill ${r.rubric.group==='problem'?'warn':''}">${r.rubric.group==='problem'?'с дефектом':'корректный'}</span> &nbsp; A: ${grade(r.arms.A.pass)} · B: ${grade(r.arms.B.pass)}</summary><div class="inside"><p>${esc(r.context)}</p>${r.files.map(f=>`<pre>${esc(f.content)}</pre>`).join('')}<details><summary>Критерии, скрытые от испытуемой модели</summary><div class="inside"><b>Должно быть в ответе</b><ul>${r.rubric.must.map(s=>`<li>${esc(s)}</li>`).join('')}</ul><b>Недопустимо</b><ul>${r.rubric.must_not.map(s=>`<li>${esc(s)}</li>`).join('')}</ul></div></details><div class="two">${response(r.arms.A,'A')}${response(r.arms.B,'B')}</div></div></details>`).join('')||'<div class="empty">Под выбранный фильтр задачи не попали.</div>'}
el('search').oninput=renderCases;el('filter').onchange=renderCases;el('expand').onclick=()=>{const ds=[...document.querySelectorAll('.case')],open=ds.some(d=>!d.open);ds.forEach(d=>d.open=open);el('expand').textContent=open?'Свернуть видимые':'Раскрыть видимые'};renderCases();
function renderSkills(){const f=el('skill-filter').value;el('skill-list').innerHTML=D.skills.filter(s=>f==='all'||f==='base'&&s.base||f==='optional'&&!s.base).map(s=>`<details><summary>${esc(s.title)}<br><span class="pill">${s.base?'Базовый':'По ситуации'}</span> <small>${esc(s.topic)}</small></summary><div class="inside"><code>/java-kotlin-${esc(s.topic)}</code><p class="subtle">${num(s.chars)} символов · SHA-256: <code>${s.sha256.slice(0,16)}…</code></p><pre>${esc(s.content)}</pre><details><summary>Прямые ссылки на источники (${s.urls.length})</summary><div class="inside source-list">${s.urls.map(u=>`<p><a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(u)}</a></p>`).join('')}</div></details></div></details>`).join('')};el('skill-filter').onchange=renderSkills;renderSkills();
el('audit-note').textContent=`Модель-оценщик завершила ${D.judge_completed} проверок пар. Дополнительная авторская проверка: ${D.manual_audit.checked.length} пар; поправок к оценке: ${D.manual_audit.overrides.length}. ${D.manual_audit.note}`;
el('run-note').textContent=`Серия ${D.run}. Вызовов внешних инструментов в A/B: ${A.tool_events+B.tool_events}; вызовов форматировщика StructuredOutput: ${A.structured_output_events+B.structured_output_events}. Расход оценщика отдельно: input ${num(D.judge_usage.input_tokens||0)}, output ${num(D.judge_usage.output_tokens||0)} токенов.`;
el('download').onclick=()=>{const u=URL.createObjectURL(new Blob([JSON.stringify(D,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download=D.run+'-benchmark-data.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};
}
el('preflights').innerHTML=`<p>Сохранено ${REPORT.preflights.rows.length} диагностических запусков: 3 короткие технические пробы и 4 ответа на задания при подборе конфигурации. Они не входят в 120 ответов основной серии. Input: ${num(REPORT.preflights.input_tokens)}, output: ${num(REPORT.preflights.output_tokens)}. Оценка CLI по прайс-листу: $${REPORT.preflights.list_cost_usd.toFixed(4)}; это не сумма списания по подписке. Прежняя неавторизованная проба дополнительно сохранена с нулевым usage.</p><ul>${REPORT.preflights.rows.map(r=>`<li><a href="${esc(r.path)}">${esc(r.path)}</a>: ${esc(r.status)}</li>`).join('')}</ul>`;
el('series-select').innerHTML=SERIES.map((s,i)=>`<option value="${i}">${esc(s.display.label)}</option>`).join('');
el('series-select').value=String(SERIES.length-1);
el('series-select').onchange=()=>{D=SERIES[Number(el('series-select').value)];renderSeries()};
el('series-overview').innerHTML='<table><thead><tr><th>Серия</th><th>Рубрика без / со скиллом</th><th>issue/ok без / со скиллом</th><th>Оценено пар</th></tr></thead><tbody>'+SERIES.map(s=>`<tr><td>${esc(s.display.label)}</td><td>${s.metrics.A.passed}/60 / ${s.metrics.B.passed}/60</td><td>${s.metrics.A.verdict_matches}/60 / ${s.metrics.B.verdict_matches}/60</td><td>${s.judge_completed}/60</td></tr>`).join('')+'</tbody></table>';
renderSeries();
</script></body></html>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='append', help='Repeat to embed multiple independent series')
    parser.add_argument('--output', default='report.html', help='Report filename within the benchmark directory')
    args = parser.parse_args()
    if Path(args.output).name != args.output:
        raise SystemExit('Output must be a filename, not a path')
    runs = args.run or ['codex-gpt61-high']
    series = [summarize(run) for run in runs]
    payload = json.dumps({'series': series, 'preflights': preflight_summary()}, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    report = TEMPLATE.replace('__DATA__', payload)
    (ROOT / args.output).write_text(report)
    summaries = []
    for data in series:
        summary = {k: data[k] for k in ['generated_utc', 'run', 'run_config', 'display', 'observed_model_ids', 'metrics', 'pairs', 'judge_completed', 'judge_usage', 'manual_audit']}
        (ROOT / 'runs' / data['run'] / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
        summaries.append(summary)
    (ROOT / 'summary.json').write_text(json.dumps({'series': summaries}, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'report': str(ROOT / args.output), 'series': [
        {k: s[k] for k in ['run', 'metrics', 'pairs']} for s in summaries]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
