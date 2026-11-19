'use strict';

/*
 * EduEval Web 前端（原生 JS，无框架）
 *
 * 三个步骤共用同一份 session 状态：
 *   0. 抽题          → GET  /api/draw（题目由系统随机抽，被试不能自选）
 *   1. 写讲稿并提交  → POST /api/sessions
 *   2. 逐轮问答      → POST /api/sessions/{id}/answers（答完一问才揭示下一问）
 *   3. 报告          → POST /api/sessions/{id}/score
 *
 * 所有规则（字数下限、轮次）都来自 /api/config，前端只做展示与校验。
 */

const STORAGE_KEY = 'edueval.sessionId';
const DRAWN_KEY = 'edueval.drawnQuestion';

const S = {
  config: null,
  drawn: null,      // 当前抽到的题目（只含题面元信息，不含采分点）
  poolSize: 0,
  session: null,
};

const $ = (id) => document.getElementById(id);

/* ---------------- 小工具 ---------------- */

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    const message = typeof detail === 'string' ? detail : `请求失败（${response.status}）`;
    throw new Error(message);
  }
  return data;
}

function showErr(id, message) {
  $(id).textContent = message || '';
}

function clearErr(id) {
  $(id).textContent = '';
}

let toastTimer = null;
function toast(message, isError = false) {
  const box = $('toast');
  box.textContent = message;
  box.classList.toggle('is-error', Boolean(isError));
  box.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => box.classList.add('hidden'), 3600);
}

function overlay(show, text) {
  $('overlay').classList.toggle('hidden', !show);
  if (text) $('overlayText').textContent = text;
}

function showPanel(name) {
  $('panelStart').classList.toggle('hidden', name !== 'start');
  $('panelAnswer').classList.toggle('hidden', name !== 'answer');
  $('panelReport').classList.toggle('hidden', name !== 'report');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function setStep(active) {
  document.querySelectorAll('#steps .step').forEach((node) => {
    const step = Number(node.dataset.step);
    node.classList.toggle('is-active', step === active);
    node.classList.toggle('is-done', step < active);
  });
}

/* ---------------- 初始化 ---------------- */

async function init() {
  try {
    S.config = await api('/api/config');
    renderTopbar();
    bindEvents();

    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        const session = await api(`/api/sessions/${encodeURIComponent(saved)}`);
        S.session = session;
        if (session.status === 'scored' && session.report) {
          renderReport(session.report, session);
        } else {
          enterAnswer(session);
        }
        return;
      } catch (err) {
        localStorage.removeItem(STORAGE_KEY);
      }
    }
    showPanel('start');
    setStep(1);
    // 恢复上次抽到的那道题；没有就现抽一道
    await drawQuestion(localStorage.getItem(DRAWN_KEY) || '');
  } catch (err) {
    toast(err.message, true);
  }
}

function renderTopbar() {
  const { model, hasKey, rounds, minScriptWords, minAnswerWords } = S.config;
  $('topbarMeta').textContent =
    `${model} · ${hasKey ? '真实调用' : '未配置密钥（仅演示模式）'} · ${rounds} 轮问答`;
  $('dryRunInput').checked = S.config.dryRunDefault;
  $('dryRunLabel').title = hasKey
    ? '勾选后用桩数据跑通流程，不消耗额度'
    : '当前没有配置 LLM_API_KEY，只能用演示模式';

  const lecture = $('lectureInput');
  lecture.dataset.min = String(minScriptWords);
  lecture.dataset.minAnswer = String(minAnswerWords);
}

function renderQuestionMeta() {
  if (!S.drawn) {
    $('questionMeta').textContent = '';
    return;
  }
  $('questionMeta').textContent =
    `题库共 ${S.poolSize} 题 · 系统随机抽取 · ${S.drawn.id}`;
}

/* ---------------- 步骤 0：抽题 ---------------- */

async function drawQuestion(questionId = '') {
  const button = $('btnRedraw');
  const start = $('btnStart');
  if (button) button.disabled = true;
  if (start) start.disabled = true;

  try {
    const query = questionId ? `?questionId=${encodeURIComponent(questionId)}` : '';
    const data = await api(`/api/draw${query}`);
    S.drawn = data.question;
    S.poolSize = data.poolSize;
    localStorage.setItem(DRAWN_KEY, S.drawn.id);
    renderDrawn();
  } catch (err) {
    S.drawn = null;
    $('drawTitle').textContent = '抽题失败';
    $('drawTask').textContent = err.message;
    $('questionMeta').textContent = '';
    toast(err.message, true);
  } finally {
    if (button) button.disabled = false;
  }
  return S.drawn;
}

function renderDrawn() {
  const q = S.drawn;
  $('drawTitle').textContent = `${q.title}（${q.grade}）`;
  $('drawTask').textContent = q.task ? `题目要求：${q.task}` : '';
  renderQuestionMeta();
  $('btnStart').disabled = false;
}

function updateLectureCount() {
  const min = S.config ? S.config.minScriptWords : 0;
  const length = $('lectureInput').value.trim().length;
  const node = $('lectureCount');
  if (length < min) {
    node.textContent = `${length} 字（还差 ${min - length} 字）`;
    node.style.color = '';
  } else {
    node.textContent = `${length} 字 ✓`;
    node.style.color = 'var(--ok)';
  }
}

function bindEvents() {
  $('btnRedraw').addEventListener('click', () => drawQuestion());
  $('lectureInput').addEventListener('input', updateLectureCount);
  $('btnStart').addEventListener('click', startSession);
  $('btnScore').addEventListener('click', runScore);
  $('btnRestart').addEventListener('click', restart);
  updateLectureCount();
}

/* ---------------- 步骤 1：创建会话 ---------------- */

async function startSession() {
  clearErr('startErr');
  if (!S.drawn) {
    showErr('startErr', '还没抽到题目，请点「换一题」重新抽取');
    return;
  }
  const lecture = $('lectureInput').value.trim();
  const min = S.config.minScriptWords;
  if (lecture.length < min) {
    showErr('startErr', `讲稿还差 ${min - lecture.length} 字（下限 ${min} 字）`);
    return;
  }

  const button = $('btnStart');
  button.disabled = true;
  button.textContent = '正在生成提问…';
  overlay(true, '正在抽取学生人设、生成 3 个提问…');

  try {
    const session = await api('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({
        questionId: S.drawn.id,
        lecture,
        candidateId: $('candidateInput').value.trim() || 'web-user',
        dryRun: $('dryRunInput').checked,
      }),
    });
    S.session = session;
    localStorage.setItem(STORAGE_KEY, session.sessionId);
    enterAnswer(session);
  } catch (err) {
    showErr('startErr', err.message);
  } finally {
    overlay(false);
    button.disabled = false;
    button.textContent = '开始评估';
  }
}

/* ---------------- 步骤 2：逐轮问答 ---------------- */

function enterAnswer(session) {
  const q = session.question;
  $('answerHint').textContent =
    `题目：${q.id} · ${q.title}（${q.grade}）　讲稿 ${session.lectureWords} 字　` +
    `${session.dryRun ? '演示模式' : '真实模型'}`;
  renderQA(session);
  showPanel('answer');
  setStep(2);
}

function nextRound(session) {
  const answered = new Set(session.answeredRounds);
  for (const q of session.questions) {
    if (!answered.has(q.round)) return q.round;
  }
  return null;
}

function renderQA(session) {
  const list = $('qaList');
  list.innerHTML = '';
  const current = nextRound(session);

  session.questions.forEach((q) => {
    if (q.answer) {
      list.appendChild(renderDoneCard(q));
    } else if (q.round === current) {
      list.appendChild(renderCurrentCard(q));
    } else {
      list.appendChild(renderLockedCard(q));
    }
  });

  const total = session.questions.length;
  const done = session.answeredRounds.length;
  const button = $('btnScore');
  button.disabled = done < total;

  if (done >= total) {
    $('answerHint').textContent = '三轮问答已完成，可以生成报告。';
  }
  scrollToCurrent();
}

function cardHead(round, personaName) {
  const head = el('div', 'qa-head');
  head.appendChild(el('span', 'qa-round', `第 ${round} 问`));
  head.appendChild(el('span', 'qa-badge', personaName));
  return head;
}

function renderCurrentCard(q) {
  const card = el('article', 'qa-card is-current');
  card.dataset.current = '1';
  card.appendChild(cardHead(q.round, q.personaName));
  card.appendChild(el('p', 'qa-text', q.text));

  const textarea = el('textarea');
  textarea.rows = 7;
  textarea.placeholder = '写下你会怎么回应这个学生……';
  card.appendChild(textarea);

  const meta = el('div', 'qa-meta');
  const counter = el('small', 'field-hint', `0 字 / 下限 ${S.config.minAnswerWords} 字`);
  const button = el('button', 'btn btn-primary', '提交这一轮');
  meta.appendChild(counter);
  meta.appendChild(button);
  card.appendChild(meta);

  textarea.addEventListener('input', () => {
    const length = textarea.value.trim().length;
    const min = S.config.minAnswerWords;
    counter.textContent = length < min ? `${length} 字 / 下限 ${min} 字` : `${length} 字 ✓`;
    counter.style.color = length < min ? '' : 'var(--ok)';
  });

  button.addEventListener('click', () => submitAnswer(q.round, textarea.value, button));
  return card;
}

function renderDoneCard(q) {
  const card = el('article', 'qa-card is-done');
  card.appendChild(cardHead(q.round, q.personaName));
  card.appendChild(el('p', 'qa-text', q.text));
  const done = el('div', 'qa-answer', q.answer);
  done.style.whiteSpace = 'pre-wrap';
  card.appendChild(done);
  return card;
}

function renderLockedCard(q) {
  const card = el('article', 'qa-card');
  card.appendChild(cardHead(q.round, q.personaName));
  card.appendChild(el('div', 'qa-locked', '⋯ 待揭示：完成上一问后显示'));
  return card;
}

async function submitAnswer(round, text, button) {
  clearErr('answerErr');
  const answer = text.trim();
  const min = S.config.minAnswerWords;
  if (answer.length < min) {
    toast(`回答至少 ${min} 字，当前 ${answer.length} 字`, true);
    return;
  }

  button.disabled = true;
  button.textContent = '提交中…';
  try {
    const session = await api(
      `/api/sessions/${encodeURIComponent(S.session.sessionId)}/answers`,
      { method: 'POST', body: JSON.stringify({ round, answer }) },
    );
    S.session = session;
    renderQA(session);
  } catch (err) {
    toast(err.message, true);
    button.disabled = false;
    button.textContent = '提交这一轮';
  }
}

function scrollToCurrent() {
  const node = document.querySelector('#qaList .qa-card[data-current="1"]');
  if (node) node.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

/* ---------------- 步骤 3：评分与报告 ---------------- */

async function runScore() {
  clearErr('answerErr');
  const button = $('btnScore');
  button.disabled = true;
  overlay(true, '正在评分（讲稿 + 3 轮问答）…');

  try {
    const report = await api(
      `/api/sessions/${encodeURIComponent(S.session.sessionId)}/score`,
      { method: 'POST' },
    );
    S.session.status = 'scored';
    S.session.report = report;
    renderReport(report, S.session);
  } catch (err) {
    showErr('answerErr', err.message);
    button.disabled = false;
  } finally {
    overlay(false);
  }
}

const RATING_CLASS = {
  '优秀': 'rating-excellent',
  '良好': 'rating-good',
  '合格': 'rating-pass',
  '待改进': 'rating-fail',
  '不合格': 'rating-fail',
};

const STATUS_ICON = { '覆盖': '✅', '部分覆盖': '⚠️', '未覆盖': '❌' };

function renderReport(report, session) {
  const panel = $('panelReport');
  panel.innerHTML = '';

  // 报告头
  const head = el('div', 'report-head');
  const left = el('div');
  left.appendChild(el('h2', 'report-title', `评估报告 · ${report.question.title}`));
  left.appendChild(el(
    'p', 'report-sub',
    `${report.question.id}（${report.question.grade}）· ${report.sessionId}` +
    (report.meta && report.meta.dry_run ? ' · 演示模式（桩数据）' : ''),
  ));
  head.appendChild(left);
  panel.appendChild(head);

  // 评级
  const hero = el('div', 'rating-hero');
  hero.appendChild(el(
    'div',
    `rating-name ${RATING_CLASS[report.rating] || ''}`,
    report.rating,
  ));
  const note = el('div', 'rating-note');
  note.textContent = report.missingCore.length
    ? `核心采分点缺失（${report.missingCore.join('、')}），已触发门槛规则，评级受限。`
    : '核心采分点已覆盖。';
  hero.appendChild(note);
  panel.appendChild(hero);

  // 统计
  const stats = el('div', 'stat-row');
  stats.appendChild(statCard(report.generalAvg.toFixed(1), '讲稿均分 / 5'));
  stats.appendChild(statCard(report.qaAvg.toFixed(1), '问答均分 / 5'));
  stats.appendChild(statCard(`${report.covered} / ${report.totalCheckpoints}`, '采分点覆盖'));
  panel.appendChild(stats);

  // 讲稿评分
  panel.appendChild(sectionTitle('讲稿评分', '通用标准 G1~G3'));
  const generalWrap = el('div');
  report.general.forEach((item) => generalWrap.appendChild(scoreRow(item)));
  panel.appendChild(generalWrap);

  // 采分点
  panel.appendChild(sectionTitle('采分点判定', `${report.covered} / ${report.totalCheckpoints} 覆盖`));
  const cpWrap = el('div');
  report.checkpoints.forEach((item) => cpWrap.appendChild(checkpointRow(item)));
  panel.appendChild(cpWrap);

  // 问答
  panel.appendChild(sectionTitle('问答评估', `${report.qa.length} 轮`));
  report.qa.forEach((round, index) => {
    const block = el('details', 'qa-report');
    if (index === 0) block.open = true;
    block.appendChild(el(
      'summary', null,
      `第 ${round.round} 轮 · ${round.personaName}　均分 ${average(round.scores).toFixed(1)} / 5`,
    ));
    block.appendChild(el('p', 'qa-text', round.question));
    block.appendChild(el('div', 'qa-answer', round.answer));
    round.scores.forEach((item) => block.appendChild(scoreRow(item)));
    panel.appendChild(block);
  });

  // 建议
  if (report.suggestions.length) {
    panel.appendChild(sectionTitle('改进建议', `${report.suggestions.length} 条`));
    const list = el('ul', 'suggestions');
    report.suggestions.forEach((text) => list.appendChild(el('li', null, text)));
    panel.appendChild(list);
  }

  // 操作
  const actions = el('div', 'report-actions');
  const download = el('a', 'btn btn-ghost', '下载 Markdown');
  download.href = `/api/sessions/${encodeURIComponent(report.sessionId)}/report.md`;
  download.setAttribute('download', `${report.sessionId}.md`);
  const again = el('button', 'btn btn-primary', '再评一次');
  again.addEventListener('click', restart);
  actions.appendChild(download);
  actions.appendChild(again);
  panel.appendChild(actions);

  // 元信息
  if (report.meta) {
    const meta = el('p', 'field-hint', '');
    meta.style.marginTop = '14px';
    meta.textContent =
      `模型 ${report.meta.model} · LLM 调用 ${report.meta.calls} 次 · ` +
      `采样 ${report.meta.samples} 次 · ${report.meta.time}`;
    panel.appendChild(meta);
  }

  showPanel('report');
  setStep(3);
}

function statCard(value, label) {
  const box = el('div', 'stat');
  box.appendChild(el('div', 'stat-value', value));
  box.appendChild(el('div', 'stat-label', label));
  return box;
}

function sectionTitle(title, hint) {
  const node = el('div', 'section');
  const head = el('h3');
  head.appendChild(document.createTextNode(title));
  if (hint) head.appendChild(el('span', 'count', hint));
  node.appendChild(head);
  return node;
}

function scoreRow(item) {
  const row = el('div', 'score-row');

  const name = el('div', 'score-name', item.name || item.dimension);
  name.appendChild(el('span', 'score-dim', item.dimension));
  row.appendChild(name);

  const number = el('div', 'score-num');
  number.appendChild(document.createTextNode(item.score.toFixed(1)));
  number.appendChild(el('small', null, ' /5'));
  row.appendChild(number);

  const body = el('div');
  const bar = el('div', 'score-bar');
  const fill = el('div', `bar-fill ${item.score < 3 ? 'low' : item.score < 4 ? 'mid' : ''}`);
  fill.style.width = `${Math.max(0, Math.min(1, item.score / 5)) * 100}%`;
  bar.appendChild(fill);
  body.appendChild(bar);

  if (item.rationale) body.appendChild(el('div', 'rationale', item.rationale));
  if (item.evidence) body.appendChild(el('div', 'evidence', `「${item.evidence}」`));
  row.appendChild(body);
  return row;
}

function checkpointRow(item) {
  const row = el('div', 'cp-row');
  row.appendChild(el('div', 'cp-status', STATUS_ICON[item.status] || '・'));
  row.appendChild(el('div', 'cp-id', item.id));

  const body = el('div');
  const desc = el('div', null, item.description);
  if (item.isCore) desc.appendChild(el('span', 'badge-core', '核心'));
  body.appendChild(desc);
  if (item.evidence) body.appendChild(el('div', 'evidence', item.evidence));
  row.appendChild(body);
  return row;
}

function average(scores) {
  if (!scores.length) return 0;
  return scores.reduce((sum, item) => sum + item.score, 0) / scores.length;
}

/* ---------------- 重新开始 ---------------- */

function restart() {
  localStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem(DRAWN_KEY);
  S.session = null;
  $('lectureInput').value = '';
  $('panelReport').innerHTML = '';
  $('qaList').innerHTML = '';
  clearErr('startErr');
  clearErr('answerErr');
  updateLectureCount();
  showPanel('start');
  setStep(1);
  drawQuestion();      // 每次重新开始都重新抽题
}

init();