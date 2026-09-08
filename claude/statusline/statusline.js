#!/usr/bin/env node
// statusLine-команда Claude Code: строка состояния под полем ввода.
// Показывает три величины, которых штатный футер вместе не дает:
// занятость контекстного окна, лимит сессии (5 часов) и недельный лимит.
//
// Вход - JSON на stdin. Нужные поля payload (проверено на 2.1.224):
//   context_window: { total_input_tokens, context_window_size, used_percentage }
//   rate_limits: { five_hour: { used_percentage, resets_at },
//                  seven_day: { used_percentage, resets_at } }
// used_percentage тут 0..100, resets_at - unix-время в секундах.
//
// rate_limits Claude Code берет из заголовков ответа API
// (anthropic-ratelimit-unified-5h/7d), поэтому до первого ответа в сессии
// их в payload просто нет. В этом случае рисуем прочерк, а не ноль:
// ноль означал бы "лимит свободен", что неправда, а неизвестность.
//
// Любая ошибка гасит вывод: пустая строка состояния лучше, чем стектрейс
// на месте интерфейса. Правило пользователя: только ASCII-пунктуация.

const RESET = '[0m';
const DIM = '[2m';
const GREEN = '[32m';
const YELLOW = '[33m';
const RED = '[31m';
const RED_BOLD = '[1;31m';

const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

function isNumber(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

// Порог красного ниже, чем кажется разумным: на 85 процентах недельного лимита
// еще есть время перепланировать работу, на 95 - уже нет.
function pctColor(pct) {
  if (!isNumber(pct)) return DIM;
  if (pct >= 95) return RED_BOLD;
  if (pct >= 85) return RED;
  if (pct >= 60) return YELLOW;
  return GREEN;
}

function formatTokens(count) {
  if (!isNumber(count) || count < 0) return '?';
  if (count >= 1000000) {
    const millions = count / 1000000;
    const rounded = millions >= 10 ? Math.round(millions) : Math.round(millions * 10) / 10;
    return rounded + 'M';
  }
  if (count >= 1000) return Math.round(count / 1000) + 'k';
  return String(count);
}

function formatClock(date) {
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return hours + ':' + minutes;
}

// Для пятичасового окна день недели избыточен, для недельного - обязателен.
function formatReset(unixSeconds, withWeekday) {
  if (!isNumber(unixSeconds) || unixSeconds <= 0) return '';
  const date = new Date(unixSeconds * 1000);
  if (Number.isNaN(date.getTime())) return '';
  const clock = formatClock(date);
  return withWeekday ? 'до ' + WEEKDAYS[date.getDay()] + ' ' + clock : 'до ' + clock;
}

function segment(label, pct, note) {
  const value = isNumber(pct) ? Math.round(pct) + '%' : '--';
  const tail = note ? ' ' + DIM + '(' + note + ')' + RESET : '';
  return DIM + label + RESET + ' ' + pctColor(pct) + value + RESET + tail;
}

function buildContextSegment(input) {
  const ctx = (input && input.context_window) || {};
  const size = ctx.context_window_size;
  const pct = ctx.used_percentage;
  if (!isNumber(size)) return segment('ctx', pct, '');
  // Пока замера нет, total_input_tokens равен нулю, но это не "контекст пуст",
  // а "еще не считали" - показываем только размер окна.
  const note = isNumber(pct) ? formatTokens(ctx.total_input_tokens) + '/' + formatTokens(size) : formatTokens(size);
  return segment('ctx', pct, note);
}

function buildLimitSegment(limits, key, label, withWeekday) {
  const limit = limits[key];
  if (!limit) return segment(label, null, '');
  return segment(label, limit.used_percentage, formatReset(limit.resets_at, withWeekday));
}

function render(input) {
  const limits = (input && input.rate_limits) || {};
  return [
    buildContextSegment(input),
    buildLimitSegment(limits, 'five_hour', 'сессия', false),
    buildLimitSegment(limits, 'seven_day', 'неделя', true),
  ].join(DIM + ' | ' + RESET);
}

let raw = '';
process.stdin.on('data', (chunk) => (raw += chunk));
process.stdin.on('end', () => {
  try {
    process.stdout.write(render(JSON.parse(raw)));
  } catch {
    // Молча: строка состояния не место для диагностики.
  }
});
