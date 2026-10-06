#!/usr/bin/env python3
"""Standalone HTML: all conclusions are derived from preserved run artifacts."""
import datetime
import html
import json
import statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parent
TITLES={'T01':'REST-контроллер','T02':'Агрегация продаж','T03':'Корутины и ошибки',
        'T04':'Java Stream и ресурсы','T05':'Ревью повторной оплаты','T06':'Ревью корректной оплаты',
        'T07':'Ревью блокирующей миграции','T08':'Ревью корректной миграции'}
E=html.escape


def load(path,default=None):return json.loads(path.read_text()) if path.exists() else default
def number(n):return f'{n:,}'.replace(',',' ')
def verdict(row):
    if row is None:return ('pending','Ожидается')
    if not row.get('valid_attempt'):
        evidence=row.get('evidence',{})
        if evidence.get('context_valid') and (row.get('returncode')!=0 or not evidence.get('client_completed')):
            return ('bad','Сбой клиента')
        return ('bad','Нарушение протокола / сбой')
    if row.get('task_pass') is True:return ('good','Пройдено')
    if row.get('task_pass') is False:return ('bad','Не пройдено')
    return ('pending','Оценка ревью ожидается')


def main():
    manifest=load(ROOT/'experiment.json');environment=load(ROOT/'environment.json')
    manual=load(ROOT/'manual-review.json',{})
    loading=load(ROOT/'skill-loading.json',{})
    posthoc=load(ROOT/'posthoc-findings.json',[])
    transport=load(ROOT/'transport-observations.json',{})
    quality=load(ROOT/'quality-review.json',[])
    rows=[]
    for spec in manifest['order']:
        row=load(ROOT/'runs'/spec['id']/'result.json')
        if row:
            row['manual']=manual.get(spec['id'])
            row['loading']=loading.get(spec['id'],{'skills':{},'names_in_initial_request':[]})
            if row['task_pass'] is None and row['manual']:
                row['task_pass']=bool(row['manual']['pass'] and row.get('review_schema_valid') and not row['protected_file_changes'])
            rows.append(row)
    by_id={r['id']:r for r in rows}
    groups={}
    for engine in ['claude','codex']:
        for arm in ['A','B']:
            items=[r for r in rows if r['engine']==engine and r['arm']==arm]
            code=[r for r in items if r['task'] in ('T01','T02','T03','T04')]
            bugs=[r for r in items if r['task'] in ('T05','T07')]
            clean=[r for r in items if r['task'] in ('T06','T08')]
            passed=lambda subset:sum(r['valid_attempt'] and r['task_pass'] is True for r in subset)
            groups[(engine,arm)]={'code':passed(code),'bugs':passed(bugs),'clean':passed(clean),
                'completed':len(items),'valid':sum(r['valid_attempt'] for r in items),
                'failed_attempts':sum(not r['valid_attempt'] for r in items),
                'input':sum(r['evidence']['usage'].get('input_total',0) for r in items),
                'output':sum(r['evidence']['usage'].get('output',0) for r in items),
                'seconds':sum(r['seconds'] for r in items),
                'median':statistics.median([r['seconds'] for r in items]) if items else None,
                'skill_used':sum(bool(r['loading']['skills']) for r in items),
                'true_findings':sum(r['manual'].get('true_findings',0) for r in items if r.get('manual')),
                'false_findings':sum(r['manual'].get('false_findings',0) for r in items if r.get('manual')),
                'hooks':sum(len(r['evidence']['hook_responses']) for r in items)}
    scored=sum(r['task_pass'] is not None or not r['valid_attempt'] for r in rows)
    complete=len(rows)==32 and scored==32
    skill_coverage={p.parent.name:{engine:sum(r['engine']==engine and r['arm']=='B' and p.parent.name in r['loading']['skills'] for r in rows)
                                  for engine in ('claude','codex')}
                    for p in sorted((ROOT/'snapshot/skills').glob('java-kotlin-*/SKILL.md'))}
    observed_skills=sum(any(counts.values()) for counts in skill_coverage.values())
    findings=load(ROOT/'conclusions.json',{'lead':'Пилот выполняется. До завершения и независимой оценки выводы о пользе обвязки не делаются.','points':[]})
    parts=['''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Java/Kotlin: обвязка с инструментами</title><style>
:root{color-scheme:dark;--bg:#10151b;--panel:#19222c;--muted:#a6b7c8;--line:#344354;--accent:#67d8c4;--good:#8fdbac;--bad:#ffaaa1;--pending:#f1d58c}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#ecf1f7;font:16px/1.6 system-ui,sans-serif}main{max-width:1180px;margin:auto;padding:48px 24px}h1{font-size:clamp(28px,5vw,46px);line-height:1.15;margin:12px 0 24px}h2{font-size:25px;margin:36px 0 14px}h3{font-size:19px}p{max-width:1000px}.eyebrow{color:var(--accent);font-size:13px;letter-spacing:.1em}.muted,small{color:var(--muted)}.lead{font-size:21px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.card,.note,details{border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:18px}.card strong{font-size:23px}.card p{margin:5px 0}.tag{font-size:13px;border:1px solid currentColor;border-radius:6px;padding:3px 7px;display:inline-block}.good{color:var(--good)}.bad{color:var(--bad)}.pending{color:var(--pending)}.table{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:13px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted)}a{color:var(--accent)}code,pre{font-family:ui-monospace,SFMono-Regular,monospace}pre{font-size:12px;line-height:1.6;white-space:pre-wrap;overflow-wrap:anywhere;background:#101821;border:1px solid var(--line);padding:14px;border-radius:8px;max-height:620px;overflow:auto}summary{cursor:pointer;font-weight:650}details{margin:10px 0}details details{background:#141d26}.controls{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}select{background:var(--panel);color:inherit;border:1px solid var(--line);padding:9px;border-radius:6px}li{margin:8px 0}.meta{font-size:13px;overflow-wrap:anywhere}.bar{height:5px;border-radius:4px;background:var(--line);overflow:hidden}.bar i{display:block;height:100%;background:var(--accent)}@media(max-width:800px){.cards{grid-template-columns:repeat(2,1fr)}main{padding:28px 16px}}@media print{body{background:white;color:black}details{break-inside:avoid}.controls{display:none}pre{max-height:none}a{color:#064}} </style><main>''']
    parts.append('<div class="eyebrow">JAVA / KOTLIN / ПИЛОТ С ИНСТРУМЕНТАМИ</div><h1>Помогает ли текущая обвязка?</h1>')
    parts.append(f'<p class="lead">{E(findings["lead"])}</p><p class="muted">{len(rows)} / 32 попытки завершены; итог зафиксирован для {scored}. '+('Серия завершена.' if complete else 'Промежуточный отчет.')+'</p>')
    for spec in manifest['order']:
        folder=ROOT/'runs'/spec['id']
        if spec['id'] in by_id or not (folder/'started.json').exists():continue
        retries=[]
        if (folder/'stdout.jsonl').exists():
            for line in (folder/'stdout.jsonl').read_text().splitlines():
                try:event=json.loads(line)
                except ValueError:continue
                if event.get('subtype')=='api_retry':retries.append(event.get('attempt'))
        active=load(folder/'started.json')
        parts.append('<p class="pending">Выполняется '+E(spec['id']+' / '+spec['engine']+' '+spec['arm']+' / '+TITLES[spec['task']])+'. Начало: '+E(active['started'])+'. Событий api_retry: '+str(len(retries))+'. Это незавершенная попытка; итог ей еще не назначен.</p>')
    parts.append(f'<div class="bar"><i style="width:{len(rows)/32*100}%"></i></div><p>A - без персональной обвязки. B - текущий общий слой. В каждой попытке один агент с файлами, терминалом и тестами.</p>')
    parts.append('<div class="cards">')
    for (engine,arm),g in groups.items():
        name='Claude Opus 5.5' if engine=='claude' else 'Codex GPT-6 Astra'
        failure_note=f'<p class="bad">Сбои или нарушения протокола: {g["failed_attempts"]}</p>' if g['failed_attempts'] else ''
        parts.append(f'<div class="card"><div class="muted">{name}</div><h3>{arm}: '+('без обвязки' if arm=='A' else 'с обвязкой')+f'</h3><p><strong>{g["code"]}/4</strong> код</p><p>{g["bugs"]}/2 дефекта найдены</p><p>{g["clean"]}/2 чистых ревью</p><small>Прошли проверки клиента и контекста: {g["valid"]}/{g["completed"]}</small>{failure_note}</div>')
    parts.append('</div><p class="muted">Неназначенная оценка не является неудачным решением. Сбой клиента или нарушение протокола сохраняется в знаменателе, но не доказывает ошибку кода или вред обвязки. Один повтор на восьми задачах не дает надежной оценки среднего эффекта.</p>')
    if findings.get('points'):parts.append('<h2>Что следует из результата</h2><ul>'+''.join('<li>'+E(s)+'</li>' for s in findings['points'])+'</ul>')
    parts.append('<h2>Что именно сравнивали</h2><div class="note"><p>Claude: <code>claude-opus-5-5 / max</code>. Codex: <code>gpt-6-astra / xhigh</code>. Одинаковые задания и исходники, свежий контекст и отдельная рабочая копия, один ответ на условие. Между собой сравниваются A/B одного клиента.</p><p>Claude B: core, правила Kotlin по paths, 30 ручных навыков и исходный ASCII-хук. У всех 30 навыков <code>disable-model-invocation: true</code>, поэтому автоматический каталог модели отсутствует. Codex B: core и Kotlin-правила в AGENTS.md, каталог 30 локальных навыков; Claude-хук не переносился.</p><p>В Codex инструменты collaboration остаются в описании даже с disable-флагами. Их фактические вызовы запрещены и проверяются. Внешний sandbox закрывает персональные инструкции, остальные попытки и скрытые проверки. Это целевая изоляция; изменяемый Gradle-кэш общий.</p></div>')
    parts.append('<h2>Результаты по задачам</h2><div class="table"><table><thead><tr><th>Задача</th><th>Claude A</th><th>Claude B</th><th>Codex A</th><th>Codex B</th></tr></thead><tbody>')
    for task,title in TITLES.items():
        parts.append(f'<tr><td>{E(title)}<br><small>{task}</small></td>')
        for engine,arm in [('claude','A'),('claude','B'),('codex','A'),('codex','B')]:
            spec=next(s for s in manifest['order'] if s['task']==task and s['engine']==engine and s['arm']==arm)
            row=by_id.get(spec['id']);klass,label=verdict(row)
            parts.append(f'<td><a class="{klass}" href="#{spec["id"]}">{label}</a></td>')
        parts.append('</tr>')
    parts.append('</tbody></table></div>')
    if posthoc:
        parts.append('<h2>Что не покрыли исходные тесты</h2>')
        for finding in posthoc:
            parts.append('<div class="note"><h3>'+E(finding['title'])+'</h3><p class="pending">'+E(finding['status'])+'</p>')
            parts.extend('<p>'+E(paragraph)+'</p>' for paragraph in finding['paragraphs'])
            parts.append('<p>'+ ' / '.join('<a href="'+E(item['path'])+'">'+E(item['label'])+'</a>' for item in finding['evidence'])+'</p></div>')
    if quality:
        parts.append('<h2>Читаемость и структура</h2><p>Дополнительная слепая проверка по конкретному контракту. Баллы за число классов, строк, интерфейсов или совпадение с формулировкой навыка не начислялись.</p>')
        for item in quality:
            parts.append('<details><summary>'+E(item['title'])+'</summary><p>'+E(item['summary'])+'</p><p><a href="'+E(item['evidence'])+'">Независимое заключение</a></p></details>')
    parts.append('<h2>Расход и применение навыков</h2><div class="table"><table><thead><tr><th>Условие</th><th>Входные токены</th><th>Выходные токены</th><th>Общее время, мин</th><th>Медиана, с</th><th>Попытки с телом навыка в контексте</th><th>Ответы хука</th></tr></thead><tbody>')
    for (engine,arm),g in groups.items():
        median=f'{g["median"]:.1f}' if g['median'] is not None else '-'
        parts.append(f'<tr><td>{engine} {arm}</td><td>{number(g["input"])}</td><td>{number(g["output"])}</td><td>{g["seconds"]/60:.1f}</td><td>{median}</td><td>{g["skill_used"]}/{g["completed"]}</td><td>{g["hooks"]}</td></tr>')
    parts.append('</tbody></table></div><p class="muted">Вход включает повторно прочитанный кэш. Это клиентские счетчики, без полной нормализации между поставщиками. Время включает инструменты и сборку. Чтение файла навыка подтверждает доступ, но не доказывает полезность. Денежное списание по подпискам не измерялось.</p>')
    transport_issues={rid: data for rid,data in transport.items() if data['responses_without_completion'] or data['same_context_resubmissions']}
    if len(transport)<len(rows):
        parts.append(f'<p class="pending">Транспортная сводка пока охватывает {len(transport)} из {len(rows)} завершенных попыток. Окончательный анализ выполняется после выхода всего запускателя, когда его HTTP-обработчики больше не могут дописывать трассы.</p>')
    if transport_issues:
        parts.append('<div class="note"><p>В трассах есть незавершенные ответы отдельных запросов или повторная отправка того же содержимого: '+E(', '.join(transport_issues))+'. Это события внутри исходной попытки, а не дополнительные попытки для выбора лучшего ответа. Время ожидания включено в итог. Клиентский usage не гарантирует учет всего расхода оборванных запросов, поэтому время и токены нельзя целиком приписать эффекту обвязки.</p><p><a href="transport-observations.json">Подробности транспорта</a></p></div>')
    if (ROOT/'transport-events.md').exists():
        parts.append('<p class="muted">В общем выводе регистратора также зафиксирован IncompleteRead без номера запроса; источник разрыва точно не установлен. <a href="transport-events.md">Диагностика и границы вывода</a>.</p>')
    if (ROOT/'reviews/transport-lifecycle.md').exists():
        parts.append('<div class="note"><p>Дополнительная проверка регистратора: закрытие Recorder не дожидается обработчиков старых HTTP-запросов. Локальный mock и авторский повтор воспроизвели ожидание и позднюю ошибку после выхода Recorder. Последовательность CLI-процессов подтверждена; отсутствие перекрытия всех локальных HTTP-операций не гарантируется. Продолжение вычисления модели на сервере и его расход не установлены. Это ограничивает сравнение времени и полноту учета; основные баллы не пересчитывались.</p><p><a href="reviews/transport-lifecycle.md">Заключение</a> / <a href="reviews/transport-lifecycle-probe.py">Проверка без сети</a> / <a href="reviews/transport-lifecycle-author-output.txt">Авторский повтор</a></p></div>')
    parts.append(f'<details><summary>Какие навыки попали в контекст: {observed_skills}/{len(skill_coverage)}</summary><p>Число завершенных попыток B с подтвержденным фрагментом содержимого. Ноль означает отсутствие наблюдения в этих задачах, а не бесполезность навыка. Полное чтение и применение каждого правила этой метрикой не доказываются.</p><div class="table"><table><thead><tr><th>Навык</th><th>Claude B</th><th>Codex B</th></tr></thead><tbody>')
    for name,counts in skill_coverage.items():
        parts.append(f'<tr><td>{E(name)}</td><td>{counts["claude"]}</td><td>{counts["codex"]}</td></tr>')
    parts.append('</tbody></table></div><p><a href="skill-loading.json">Якоря текста в фактических запросах</a></p></details>')
    parts.append('<h2>Проверки и воспроизводимость</h2><p>До старта эталоны прошли независимые тесты, дефекты/мутации были отвергнуты: 16/16 проверок. В PostgreSQL измерены реальные режимы pg_locks. Отдельные ревью исправили дефекты самих тестов и проверки запрета делегирования до заморозки.</p>')
    parts.append('<p>Содержание ответов ревью оценивает отдельная модельная сессия по анонимным пакетам; основная сессия сверяет заключение с кодом, контрактом и исполняемыми доказательствами. Это проверка ассистентами, без человеческой разметки. Корректность написанного кода оценивается отдельными фиксированными тестами.</p>')
    parts.append(f'<p class="meta">Заморожено: {E(manifest["frozen_at"])}<br>Исходный commit: {E(environment["source_commit"])}<br>Digest входов: {E(manifest["input_digest"])}<br>Seed порядка попыток: {manifest["seed"]}. Все попытки сохранены, выбор лучшего ответа не выполнялся.</p>')
    parts.append('<p><a href="experiment.json">Манифест</a> / <a href="environment.json">Окружение</a> / <a href="preflight-summary.json">Технические пробы</a> / <a href="reviews/fixtures.md">Ревью заданий</a> / <a href="reviews/runner.md">Ревью запускателя</a> / <a href="manual-review.json">Оценка ревью</a></p>')
    parts.append(f'<p><a href="{E(manifest["fixture_validation"])}/summary.json">16 проверок эталонов и мутаций</a> / <a href="NEXT_EXPERIMENT.md">Проект следующей серии из 30 задач</a></p>')
    if (ROOT/'reviews/final-report.md').exists():
        parts.append('<p><a href="reviews/final-report.md">Независимая финальная сверка отчета</a> / <a href="report-validation.json">Статическая проверка HTML и входов</a></p>')
    if (ROOT/'credential-scan.json').exists():
        parts.append('<p><a href="credential-scan.json">Проверка сохраненных трасс на признаки учетных данных</a>. Это ограниченный поиск ключей и шаблонов, а не доказательство отсутствия любых секретов.</p>')
    parts.append('<details><summary>Полный протокол и источники</summary><pre>'+E((ROOT/'PROTOCOL.md').read_text())+'</pre></details>')
    parts.append('<p class="meta">Методика: <a href="https://developers.openai.com/blog/eval-skills">OpenAI: eval skills</a> / <a href="https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents">Anthropic: agent evals</a> / <a href="https://www.anthropic.com/engineering/infrastructure-noise">Infrastructure noise</a> / <a href="https://code.claude.com/docs/en/skills">Claude: навыки и активация</a>.</p>')
    parts.append('<h2>Все попытки и доказательства</h2><div class="controls"><select id="engine"><option value="all">Оба клиента</option value="claude">Claude</option><option value="codex">Codex</option></select><select id="arm"><option value="all">Оба условия</option><option value="A">A: без обвязки</option><option value="B">B: с обвязкой</option></select></div>')
    for spec in manifest['order']:
        row=by_id.get(spec['id']);rid=spec['id'];klass,label=verdict(row)
        parts.append(f'<details class="run" id="{rid}" data-engine="{spec["engine"]}" data-arm="{spec["arm"]}"><summary>{rid} / {spec["engine"]} {spec["arm"]} / {E(TITLES[spec["task"]])} <span class="tag {klass}">{label}</span></summary>')
        if row:
            ev=row['evidence'];usage=ev['usage']
            parts.append(f'<p>{row["seconds"]:.1f} с; вход {number(usage.get("input_total",0))}, выход {number(usage.get("output",0))} токенов. Запросов модели: {ev["model_requests"]}.</p>')
            if not row['valid_attempt']:
                reasons=[]
                if row['returncode']!=0:reasons.append('Код завершения клиента: '+str(row['returncode'])+'.')
                if not ev['client_completed']:reasons.append('Клиент не сообщил успешное завершение задачи.')
                if not ev['context_valid']:reasons.append('Контекст или вызовы инструментов не соответствуют протоколу.')
                if not reasons:reasons.append('Параметры модели не соответствуют замороженному условию; см. полный результат.')
                parts.append('<p class="bad">'+E(' '.join(reasons))+' Проверка сохраненных файлов не превращает прерванную работу в завершенное решение.</p>')
            parts.append('<p class="meta">Фактический контекст: core='+str(ev['core_present'])+', Kotlin='+str(ev['kotlin_rule_present'])+', имен навыков в первом запросе='+str(len(row['loading']['names_in_initial_request']))+'. Недопустимое делегирование: '+E(json.dumps(ev['forbidden_delegation']))+'.</p>')
            parts.append('<p>Подтверждено содержимое навыков: '+E(', '.join(row['loading']['skills']) or 'нет')+'.</p>')
            if rid in transport_issues:
                parts.append('<details><summary>Повторы и завершение ответов</summary><pre>'+E(json.dumps(transport_issues[rid],ensure_ascii=False,indent=2))+'</pre></details>')
            if row.get('grader'):parts.append('<p>Независимые тесты: <code>'+E(json.dumps(row['grader']['counts']))+'</code>.</p>')
            if row.get('manual'):parts.append('<p>Проверка содержания ревью: '+E(row['manual'].get('reason',''))+'</p>')
            for finding in posthoc:
                if rid in finding['runs']:
                    parts.append('<p class="pending">Дополнительное наблюдение: '+E(finding['title'])+'. Основная оценка относится только к замороженным проверкам.</p>')
            if row['protected_file_changes']:parts.append('<p class="bad">Изменены защищенные файлы: '+E(', '.join(row['protected_file_changes']))+'</p>')
            parts.append('<details><summary>Задание</summary><pre>'+E((ROOT/'runs'/rid/'prompt.txt').read_text())+'</pre></details>')
            if row.get('review') is not None:parts.append('<details><summary>review.json</summary><pre>'+E(json.dumps(row['review'],ensure_ascii=False,indent=2))+'</pre></details>')
            parts.append('<details><summary>Ответ агента</summary><pre>'+E(ev['final'])+'</pre></details>')
            diff=(ROOT/'runs'/rid/'change.diff').read_text()
            if diff:parts.append('<details><summary>Изменения кода и добавленные тесты</summary><pre>'+E(diff)+'</pre></details>')
            skill_data={'calls':ev['skill_calls'],'file_accesses':ev['skill_file_accesses']}
            if any(skill_data.values()):parts.append('<details><summary>Обращения к навыкам</summary><pre>'+E(json.dumps(skill_data,ensure_ascii=False,indent=2))+'</pre></details>')
            parts.append(f'<p><a href="runs/{rid}/result.json">Полный результат</a> / <a href="runs/{rid}/stdout.jsonl">События клиента</a> / <a href="runs/{rid}/command.json">Команда</a></p>')
        parts.append('</details>')
    parts.append('<p class="muted meta">Основные результаты, тексты ответов, диффы и протокол встроены в этот HTML. Ссылки на сырые трассы требуют соседнего каталога доказательств. Сформировано '+E(datetime.datetime.now(datetime.timezone.utc).isoformat())+'.</p>')
    parts.append('''</main><script>function filter(){document.querySelectorAll('.run').forEach(r=>r.hidden=!(['engine','arm'].every(k=>document.getElementById(k).value==='all'||r.dataset[k]===document.getElementById(k).value)))}document.querySelectorAll('select').forEach(e=>e.addEventListener('change',filter));function focusHash(){let el=document.getElementById(location.hash.slice(1));if(el&&el.classList.contains('run')){el.hidden=false;el.open=true}}addEventListener('hashchange',focusHash);focusHash();</script></html>''')
    (ROOT/'report.html').write_text(''.join(parts))
    summary={'completed':len(rows),'scored':scored,'complete':complete,'groups':{engine+'-'+arm:g for (engine,arm),g in groups.items()},
             'posthoc_findings':[{'id':f['id'],'runs':f['runs'],'status':f['status']} for f in posthoc]}
    summary['transport_affected_attempts']=sorted(transport_issues)
    summary['skill_coverage']=skill_coverage
    summary['skills_observed']=observed_skills
    (ROOT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
