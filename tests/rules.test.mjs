import test from 'node:test';
import assert from 'node:assert/strict';
import { calculate, validateScore, dimensions } from '../lib/rules.mjs';
import { examples } from '../lib/fixtures.mjs';
test('权重、边界与否决优先级',()=>{
  assert.equal(calculate([5,5,4,5,5]).total,97);
  assert.equal(calculate([5,4,4,4,5]).total,89);
  assert.equal(calculate([1,5,5,5,5]).verdict,'未过');
  assert.equal(calculate([3,3,3,3,3]).verdict,'待定');
  assert.equal(calculate([2,5,5,5,5]).verdict,'待定');
  assert.equal(calculate([5,2,2,5,5]).verdict,'待定');
  assert.equal(calculate([2,2,2,2,2]).verdict,'未过');
  assert.throws(()=>calculate([6,4,3,4,5]));
});
test('所有示例引用都能在对应轮次找到；不接受伪造证据',()=>{
  for(const f of Object.values(examples)) {
    const raw={dimensions:dimensions.map((d,i)=>({name:d.name,level:f.levels[i],rationale:f.reasons[i],evidence:[{round:f.evidenceRounds[i],quote:f.quotes[i]}]})),profile_tags:['标签一','标签二'],suggestions:f.tips};
    const rounds=f.answers.map(text=>({text}));
    assert.equal(validateScore(raw,rounds).total,89);
    raw.dimensions[0].evidence[0].quote='原文不存在的任意引用';
    assert.throws(()=>validateScore(raw,rounds),/不存在/);
  }
});
