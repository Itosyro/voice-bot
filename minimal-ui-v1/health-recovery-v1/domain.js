// Pure domain operations. Kept in parity with domain.py by fixture tests.
const healthDomain = (() => {
  const copy=v=>JSON.parse(JSON.stringify(v));
  const ratings=['energy','mood','stress','soreness','wellbeing'];
  const fail=message=>{throw Error(message)};
  function day(v) { if(typeof v!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(v)||!Number.isFinite(Date.parse(v))||new Date(v).toISOString().slice(0,10)!==v) fail('Дата: ГГГГ-ММ-ДД'); return v; }
  // Frozen Python/ECMAScript whitespace union, identical to domain.py.
  function text(v,max=1000) {if(typeof v!=='string'||[...v].length>max) fail('Проверь текст');return v.replace(/^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+|[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+$/g,'');}
  function number(v,min,max) {if(typeof v!=='number'||!Number.isFinite(v)||v<min||v>max) fail(`Число от ${min} до ${max}`);return v;}
  function rating(v){number(v,1,5);if(!Number.isInteger(v))fail('Оценка: целое число 1–5');return v;}
  function clock(v){if(typeof v!=='string'||!/^([01]\d|2[0-3]):[0-5]\d$/.test(v))fail('Укажи точное время ЧЧ:ММ');return +v.slice(0,2)*60+ +v.slice(3);}
  function id(v){if(typeof v!=='string'||['__proto__','constructor','prototype'].includes(v)||!/^[-\w]{1,80}$/.test(v))fail('Нужен устойчивый ID');return v;}
  function zone(v){if(typeof v!=='string'||!/^[A-Za-z][A-Za-z0-9_+/-]*$/.test(v)||['factory','localtime'].includes(v.toLowerCase()))fail('Укажи часовой пояс');try{new Intl.DateTimeFormat('en',{timeZone:v})}catch{fail('Неизвестный часовой пояс')}return v;}
  const weekday=d=>(new Date(d+'T12:00:00Z').getUTCDay()+6)%7;
  function safeKeys(value){
    if(value&&typeof value==='object')for(const key of Object.keys(value)){
      if(['__proto__','constructor','prototype'].includes(key))fail('Небезопасное поле');
      safeKeys(value[key]);
    }
  }
  function deriveSleep(row,d){
    if(row.durationKind==='reported')for(const key of ['start','end','startDay'])delete row[key];
    else if(row.durationKind==='clock'||(!Object.hasOwn(row,'durationKind')&&Object.hasOwn(row,'start')&&Object.hasOwn(row,'end'))){
      try{const a=clock(row.start),b=clock(row.end),minutes=(b-a+1440)%1440;if(!minutes)fail('ambiguous clocks');row.startDay=new Date(Date.parse(day(d))-(a>b?86400000:0)).toISOString().slice(0,10);row.durationMinutes=minutes;}
      catch{delete row.durationMinutes;delete row.startDay;}
    }
    return row;
  }
  function apply(state,action,p){
    if(!p||typeof p!=='object'||Array.isArray(p))fail('Неверные данные');
    safeKeys(p);
    const d=day(p.day),old=Object.hasOwn(state,'healthRecovery')?state.healthRecovery:{};
    if(!old||typeof old!=='object'||Array.isArray(old))fail('Неверные данные');
    if(old.version!==undefined&&old.version!==1)fail('Обнови приложение: новая версия данных');
    const h=copy(old),tz=zone(Object.hasOwn(p,'timezone')?p.timezone:h.timezone),source=Object.hasOwn(p,'source')?p.source:'ai';
    if(!['manual','ai'].includes(source))fail('Неизвестный источник');
    const common={day:d,timezone:tz,source,updatedAt:new Date().toISOString()};if('note'in p)common.note=text(p.note);
    const fields={health_sleep:['start','end','durationMinutes','quality'],health_checkin:ratings,health_supplement_schedule:['id','name','dose','slots','weekdays','enabled','update'],health_supplement_mark:['scheduleId','slotId','status']}[action];
    if(!fields||Object.keys(p).some(k=>!['day','timezone','source','note',...fields].includes(k)))fail('Неизвестное поле');
    if(action==='health_sleep'){
      h.sleep||={};const row={...h.sleep[d],...common};
      if('quality'in p)row.quality=rating(p.quality);
      if('start'in p||'end'in p){
        const start=Object.hasOwn(p,'start')?p.start:row.start,end=Object.hasOwn(p,'end')?p.end:row.end,a=clock(start),b=clock(end),minutes=(b-a+1440)%1440;
        if(!minutes||'durationMinutes'in p)fail('Укажи время или длительность; одинаковые времена неоднозначны');
        Object.assign(row,{start,end,startDay:new Date(Date.parse(d)-(a>b?86400000:0)).toISOString().slice(0,10),durationMinutes:minutes,durationKind:'clock'});
      }else if('durationMinutes'in p){row.durationMinutes=number(p.durationMinutes,1,1440);row.durationKind='reported';delete row.start;delete row.end;delete row.startDay;}
      deriveSleep(row,d);
      if(!('durationMinutes'in row))fail('Укажи время сна или длительность');h.sleep[d]=row;
    }else if(action==='health_checkin'){
      if(!Object.keys(p).some(k=>['note',...ratings].includes(k)))fail('Добавь оценку или заметку');
      h.checkins||={};const row={...h.checkins[d],...common};for(const k of ratings)if(k in p)row[k]=rating(p[k]);h.checkins[d]=row;
    }else if(action==='health_supplement_schedule'){
      const sid=id(p.id);h.schedules||={};const before=h.schedules[sid]||{},row={...before,...common,id:sid};
      if('update'in p&&typeof p.update!=='boolean')fail('Проверь update');
      if(p.update&&!h.schedules[sid])fail('Расписание для изменения не найдено');
      for(const k of fields)if(k in p&&k!=='update')row[k]=copy(p[k]);
      for(const k of ['name','dose']){row[k]=text(row[k],240);if(!row[k])fail('Название и доза — только со слов пользователя');}
      if(!Array.isArray(row.slots)||!row.slots.length||row.slots.length>12)fail('Добавь 1–12 точных времён');
      const seen=new Set();for(const s of row.slots){id(s.id);clock(s.time);if(seen.has(s.id))fail('Повтор ID слота');seen.add(s.id);}
      row.slots=row.slots.map(s=>({...before.slots?.find(o=>o.id===s.id),...s}));
      if(!Array.isArray(row.weekdays)||!row.weekdays.length||row.weekdays.some(x=>!Number.isInteger(x)||x<0||x>6)||new Set(row.weekdays).size!==row.weekdays.length)fail('Выбери дни недели');
      if(typeof row.enabled!=='boolean')fail('Проверь включение расписания');h.schedules[sid]=row;
    }else{
      const sid=id(p.scheduleId),slotid=id(p.slotId),schedule=h.schedules?.[sid],slot=schedule?.slots.find(s=>s.id===slotid);
      if(!schedule?.enabled||!schedule.weekdays.includes(weekday(d))||!slot)fail('Слот недоступен на этот день');
      if(!['taken','skipped','pending'].includes(p.status))fail('Неизвестная отметка');
      const key=`${d}/${sid}/${slotid}`;h.intakes||={};const before=h.intakes[key]||{};
      if(before.status===p.status&&(!('note'in p)||p.note===before.note))return key;
      h.intakes[key]={...before,...common,id:key,scheduleId:sid,slotId:slotid,status:p.status,snapshot:before.snapshot||{name:schedule.name,dose:schedule.dose,time:slot.time,timezone:schedule.timezone}};
    }
    h.version=1;h.timezone=tz;state.healthRecovery=h;return d;
  }
  const record=v=>v&&typeof v==='object'&&!Array.isArray(v)?v:{};
  function summaryDomain(value,d){
    const h=copy(record(value));
    if(h.version!==undefined&&h.version!==1)return {};
    const validDay=v=>{try{return day(v)<=d}catch{return false}};
    for(const kind of ['sleep','checkins']){
      const rows={};
      for(const [k,v]of Object.entries(record(h[kind]))){
        if(!validDay(k)||v!==record(v))continue;
        if(kind==='sleep')deriveSleep(v,k);
        for(const key of kind==='sleep'?['durationMinutes','quality']:ratings){
          if(!Object.hasOwn(v,key))continue;
          try{key==='durationMinutes'?number(v[key],1,1440):rating(v[key])}catch{delete v[key]}
        }
        if(kind!=='sleep'||Object.hasOwn(v,'durationMinutes'))rows[k]=v;
      }
      h[kind]=rows;
    }
    const schedules={};
    for(const [sid,s]of Object.entries(record(h.schedules))){
      try{
        id(sid);
        if(s!==record(s)||typeof s.enabled!=='boolean'||!Array.isArray(s.weekdays)||s.weekdays.some(v=>!Number.isInteger(v)||v<0||v>6)||['name','dose','timezone'].some(k=>typeof s[k]!=='string')||!Array.isArray(s.slots))continue;
        for(const slot of s.slots){id(record(slot).id);clock(slot.time)}
        schedules[sid]=s;
      }catch{}
    }
    h.schedules=schedules;
    h.intakes=Object.fromEntries(Object.entries(record(h.intakes)).filter(([k,r])=>r===record(r)&&typeof r.id==='string'&&validDay(r.day)&&['pending','taken','skipped'].includes(r.status)&&r.snapshot===record(r.snapshot)));
    return h;
  }
  function summary(state,d){
    day(d);const h=summaryDomain(state.healthRecovery,d),rows=h.sleep||{},days=Object.keys(rows).filter(k=>k<=d).sort(),week=days.filter(k=>(Date.parse(d)-Date.parse(k))/86400000<7).map(k=>rows[k].durationMinutes).filter(n=>typeof n==='number');
    const sleep=rows[d],checkin=Object.keys(h.checkins?.[d]||{}).length?h.checkins[d]:undefined,factors=[];
    if(!sleep)factors.push(days.length?'stale sleep':'missing sleep');
    if(!checkin)factors.push(Object.keys(h.checkins||{}).some(k=>k<d)?'stale check-in':'missing check-in');
    for(const k of ratings)if(checkin?.[k]===undefined)factors.push('missing '+k);
    let low=false;
    if(sleep){factors.push(`sleep ${sleep.durationMinutes} minutes (under 360 lowers recovery)`);low=sleep.durationMinutes<360||(sleep.quality??3)<=2;}
    for(const k of ratings)if(checkin?.[k]!==undefined){factors.push(`${k} ${checkin[k]}/5`);low||=['stress','soreness'].includes(k)?checkin[k]>=4:checkin[k]<=2;}
    const level=!sleep||!ratings.some(k=>checkin?.[k]!==undefined)?'insufficient_data':low?'low':sleep.durationMinutes>=420&&checkin.energy>=4&&checkin.wellbeing>=4?'high':'normal';
    factors.push('Training readiness uses its existing 0–3 scale; no conversion. Review training and Jump context separately.');
    const context={};
    for(const [label,readiness]of [['training',state.trainingHub?.readiness],['jump',state.jumpLab?.today?.readiness]]){
      const recordedDay=readiness?.localDate||readiness?.day;
      const freshness=!readiness?'missing':!recordedDay?'undated':recordedDay===d?'current':'stale';
      context[label]={readiness:readiness??null,freshness};factors.push(label+' context '+freshness);
    }
    const slots=[];
    for(const [sid,s]of Object.entries(h.schedules||{}))if(s.enabled&&s.weekdays.includes(weekday(d)))for(const slot of s.slots){const key=`${d}/${sid}/${slot.id}`;slots.push(h.intakes?.[key]||{id:key,day:d,scheduleId:sid,slotId:slot.id,status:'pending',snapshot:{name:s.name,dose:s.dose,time:slot.time,timezone:s.timezone}});}
    return {day:d,timezone:h.timezone??null,sleep:{last:days.length?rows[days.at(-1)]:null,mean7Minutes:week.length?week.reduce((a,b)=>a+b,0)/week.length:null,recordedDays:week.length,history:days.reverse().map(k=>rows[k])},checkin:checkin||null,supplements:{today:slots,remaining:slots.filter(r=>r.status==='pending'),history:Object.values(h.intakes||{}).sort((a,b)=>b.id.localeCompare(a.id))},readiness:{level,factors,clinical:false,context,trainingReference:state.trainingHub??null,jumpReference:state.jumpLab??null}};
  }
  function today(timezone){return new Intl.DateTimeFormat('en-CA',{timeZone:zone(timezone),year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());}
  return {apply,summary,today,ratings};
})();
window.DVIZH_HEALTH=Object.freeze(healthDomain);
