// Domain and persisted-data regression checks. Browser UX is verified separately.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const base=path.join(__dirname,'../codexai-site/dist/demos');
const slugs=['chore-bank','weekend-planner','screen-agreement','family-trip','habit-board','sorting-challenge','reading-exchange','story-director'];
function load(slug,{raw,failSave=false}={}){
 const elements=new Map();
 const element=()=>({innerHTML:'',textContent:'',style:{setProperty(){}},dataset:{},addEventListener(){},focus(){},showModal(){},close(){},insertAdjacentHTML(){}});
 const document={querySelector(s){if(!elements.has(s))elements.set(s,element());return elements.get(s)},querySelectorAll(){return[]},documentElement:element(),body:element()};
 const writes=[];
 const context=vm.createContext({window:{scrollTo(){}},document,console,Date,crypto:{randomUUID:()=> 'test-id'},setTimeout(){},clearTimeout(){},setInterval(){},localStorage:{getItem:()=>raw||null,setItem(k,v){if(failSave)throw Error('quota');writes.push([k,v])}},URL,Blob});
 for(const file of ['data/course.js','data/seed.js'])vm.runInContext(fs.readFileSync(path.join(base,slug,file),'utf8'),context);
 vm.runInContext(fs.readFileSync(path.join(base,'studio.js'),'utf8'),context);
 vm.runInContext(fs.readFileSync(path.join(base,slug,'studio-app.js'),'utf8'),context);
 return {run:code=>vm.runInContext(code,context),elements,writes};
}
for(const slug of slugs){
 test(`${slug}: seed, three views and legacy v2 backup`,()=>{
  const app=load(slug);
  for(let i=0;i<3;i++){app.run(`active=${i};render()`);assert.ok(app.elements.get('#app').innerHTML.length>50)}
  assert.equal(app.run('validateBackup({kind:"maker-product",id:C.id,version:2,state:clone(state)})===undefined'),false);
  assert.equal(app.run('validateBackup({kind:"maker-product",id:C.id,version:2,state:clone(seed)})===undefined'),false);
 });
 test(`${slug}: corrupt local data is preserved`,()=>{
  const app=load(slug,{raw:'{broken json'});assert.equal(app.run('storageOK'),false);app.run('save()');assert.equal(app.writes.length,0);
 });
}
test('reject another course backup and malicious identifiers before restore',()=>{
 const app=load('chore-bank');
 assert.throws(()=>app.run('validateBackup({kind:"maker-product",id:"18",version:2,state:clone(seed)})'));
 assert.throws(()=>app.run(`const bad=clone(seed);bad.tasks[0].id='a" onclick="alert(1)';validateBackup({kind:'maker-product',id:C.id,version:2,state:bad})`));
 assert.throws(()=>app.run(`const duplicate=clone(seed);duplicate.tasks[1].id=duplicate.tasks[0].id;validateBackup({kind:'maker-product',id:C.id,version:2,state:duplicate})`));
 assert.throws(()=>app.run(`const negative=clone(seed);negative.tasks[0].points=-5;validateBackup({kind:'maker-product',id:C.id,version:2,state:negative})`));
});
test('overlap and required rest are both detected, exact rest is allowed',()=>{
 const app=load('weekend-planner');
 app.run(`state.tasks=[{id:'a',day:'周六',start:'09:00',end:'10:00'}];p.gap=15`);
 assert.equal(app.run(`conflicts({id:'b',day:'周六',start:'09:45',end:'10:30'}).length`),1);
 assert.equal(app.run(`conflicts({id:'b',day:'周六',start:'10:10',end:'11:00'}).length`),1);
 assert.equal(app.run(`conflicts({id:'b',day:'周六',start:'10:15',end:'11:00'}).length`),0);
 assert.equal(app.run(`conflicts({id:'b',day:'周日',start:'09:00',end:'10:00'}).length`),0);
});
test('redeemed points are subtracted, unfinished points are not spendable',()=>{
 const app=load('chore-bank');app.run('state.weeks=[{points:16}];p.redemptions=[{cost:15}]');assert.equal(app.run('balance()'),1);assert.equal(app.run('pending()'),3);
});
test('timer uses wall clock and paused duration stays fixed',()=>{
 const app=load('screen-agreement');app.run('p.timerV3={elapsed:30000,started:null,limit:45}');assert.equal(app.run('timerElapsed()'),30000);
 app.run('p.timerV3.started=Date.now()-65000');assert.ok(app.run('timerElapsed()')>=95000);
});
test('story graph catches unreachable and missing scenes',()=>{
 const app=load('story-director');assert.equal(app.run('graphCheck().endings.length'),3);
 app.run(`state.nodes.orphan={title:'test',text:'test',ending:true}`);assert.equal(app.run('graphCheck().unreachable.includes("orphan")'),true);
 app.run(`state.nodes.start.choices.push({label:'bad',next:'missing'})`);assert.equal(app.run('graphCheck().missing.includes("missing")'),true);
 assert.throws(()=>app.run(`validateBackup({kind:'maker-product',id:C.id,version:2,state:clone(state)})`));
});
test('double-tapping an answer cannot award points twice',()=>{
 const app=load('sorting-challenge');app.run(`startRound();answer('可回收物');answer('可回收物')`);assert.equal(app.run('p.round.score'),1);
});
test('failed storage never announces a successful save',()=>{
 const app=load('habit-board',{failSave:true});app.run('commit()');assert.match(app.elements.get('#toast').textContent,/未能保存/);assert.equal(app.writes.length,0);
});
