export const dimensions = [
  { name: '学科准确性', weight: 25 }, { name: '讲解逻辑', weight: 20 },
  { name: '表达清晰度', weight: 15 }, { name: '学情适配', weight: 20 },
  { name: '错因诊断', weight: 20 },
];
export const rubricVersion = 'demo-0.2-text';
export function calculate(levels) {
  if (!Array.isArray(levels) || levels.length !== 5 || levels.some(v => !Number.isInteger(v) || v < 1 || v > 5)) throw new Error('五个档位必须是 1–5 的整数');
  const total = Math.round(levels.reduce((sum, v, i) => sum + v * dimensions[i].weight, 0) / 5);
  const veto = levels[0] === 1;
  // Explicit demo completion of the ambiguous source rule: multiple low dimensions => pending review.
  const verdict = veto || total < 60 ? '未过' : total >= 70 && levels.every(v => v >= 3) ? '通过' : '待定';
  return { total, verdict, veto };
}
export function validateScore(raw, rounds) {
  if (!raw || !Array.isArray(raw.dimensions) || raw.dimensions.length !== 5) throw new Error('模型未返回完整的五维评分');
  const checked = dimensions.map(d => {
    const matches = raw.dimensions.filter(v => v.name === d.name);
    if (matches.length !== 1) throw new Error(`评分维度重复或缺失：${d.name}`);
    const item = matches[0];
    if (!Number.isInteger(item.level) || item.level < 1 || item.level > 5) throw new Error('评分档位超出范围');
    if (typeof item.rationale !== 'string' || !item.rationale.trim() || item.rationale.length > 3000) throw new Error('评分理由无效');
    if (!Array.isArray(item.evidence) || !item.evidence.length || item.evidence.length > 5) throw new Error('缺少评分证据');
    const evidence = item.evidence.map(e => {
      if (!Number.isInteger(e.round) || typeof e.quote !== 'string' || e.quote.trim().length < 4 || e.quote.length > 1200 || !rounds[e.round - 1]?.text.includes(e.quote)) throw new Error('模型引用了回答中不存在的证据，请重试或人工复核');
      return { round: e.round, quote: e.quote };
    });
    return { ...d, level: item.level, rationale: item.rationale, evidence };
  });
  for (const [name, min, max] of [['profile_tags',2,4],['suggestions',1,3]]) {
    if (!Array.isArray(raw[name]) || raw[name].length < min || raw[name].length > max || raw[name].some(x => typeof x !== 'string' || !x.trim() || x.length > 2000)) throw new Error(`模型返回的 ${name} 无效`);
  }
  return { dimensions: checked, ...calculate(checked.map(d => d.level)), tags: raw.profile_tags, suggestions: raw.suggestions, rubricVersion };
}
