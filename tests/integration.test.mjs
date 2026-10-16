import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { once } from 'node:events';
import { examples } from '../lib/fixtures.mjs';
import { dimensions } from '../lib/rules.mjs';
const fixture=examples['M-CZ-0031'];
const score={dimensions:dimensions.map((d,i)=>({name:d.name,level:fixture.levels[i],rationale:fixture.reasons[i],evidence:[{round:fixture.evidenceRounds[i],quote:fixture.quotes[i]}]})),profile_tags:['概念清晰','诊断有据'],suggestions:fixture.tips};
test('完整 API 流程、阶段保护、复核和真正经过 Pi SDK 的模拟上游', {timeout:60000}, async()=>{
  let requests=0;
  const upstream=http.createServer(async(req,res)=>{
    let text=''; for await(const c of req) text+=c;
    const b=JSON.parse(text); requests++;
    assert.equal(req.headers.authorization,'Bearer test-key');
    assert.equal(b.model,'test-qwen');
    assert.ok(!b.tools?.length);
    const content=JSON.stringify(score);
    res.writeHead(200,{'Content-Type':'text/event-stream'});
    for(const chunk of [{role:'assistant',content},{},]) res.write(`data: ${JSON.stringify({id:'test-1',object:'chat.completion.chunk',created:1,model:'test-qwen',choices:[{index:0,delta:chunk,finish_reason:chunk.content?null:'stop'}]})}\n\n`);
    res.end('data: [DONE]\n\n');
  });
  upstream.listen(0,'127.0.0.1'); await once(upstream,'listening');
  const port=33219;
  Object.assign(process.env,{PORT:String(port),MODEL_BASE_URL:`http://127.0.0.1:${upstream.address().port}/v1`,MODEL_API_KEY:'test-key',MODEL_ID:'test-qwen'});
  const {server}=await import('../server.mjs');
  let logs='';
  try {
    if(!server.listening) await once(server,'listening');
    const request=async(route,data,token)=>{ const r=await fetch(`http://127.0.0.1:${port}${route}`,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},...(data===undefined?{}:{body:JSON.stringify(data)})});return {status:r.status,data:await r.json()};};
    assert.equal((await request('/api/scenarios')).data.length,20);
    const forbidden=await fetch(`http://127.0.0.1:${port}/api/assessments`,{method:'POST',headers:{Origin:'https://other.example'},body:'{}'});assert.equal(forbidden.status,403);
    for(const mode of ['demo','live']) {
      let {data:a}=await request('/api/assessments',{scenarioId:'M-CZ-0031',mode});const token=a.token;const route=`/api/assessments/${a.id}`;
      assert.equal((await request(route+'/score',{},token)).status,400);
      assert.equal((await request(route+'/answer',{round:2,text:fixture.answers[1]},token)).status,409);
      assert.ok(!JSON.stringify(a).includes(fixture.questions[1]));
      if(mode==='demo') assert.equal((await request(route+'/answer',{round:1,text:'任意自定义文本任意自定义文本任意自定义文本'},token)).status,400);
      for(let i=0;i<3;i++){const next=await request(route+'/answer',{round:i+1,text:fixture.answers[i]},token);assert.equal(next.status,200);a=next.data;}
      const result=await request(route+'/score',{},token);assert.equal(result.status,200,JSON.stringify(result.data)+logs);assert.equal(result.data.total,89);assert.equal(result.data.mode,mode);
      const review=await request(route+'/review',{levels:[4,4,4,4,4],note:'本机测试复核意见'},token);assert.equal(review.data.total,89);assert.equal(review.data.review.total,80);
      assert.equal((await request(route,undefined,'wrong-token')).status,404);
    }
    assert.equal(requests,1,'真实模式必须经过一次 Pi 上游请求，示例模式不得请求');
  } finally { server.closeAllConnections(); await new Promise(resolve=>server.close(resolve)); upstream.closeAllConnections(); await new Promise(resolve=>upstream.close(resolve)); }
});
