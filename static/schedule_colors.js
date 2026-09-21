/* Stable scene families; stages and connectors derive their color from the parent. */
window.ScheduleColors = (() => {
  const families = [
    {id:'work',label:'工作 / 科研',hue:218,color:'#6684c9',description:'论文、项目、会议、面试与宣讲'},
    {id:'entertainment',label:'娱乐 / 旅行',hue:35,color:'#d09448',description:'旅行、演出、唱歌与休闲'},
    {id:'health',label:'健康',hue:155,color:'#55a78b',description:'就医、运动、按摩与体检'},
    {id:'growth',label:'个人发展',hue:274,color:'#a47bca',description:'学习、课程、阅读与技能提升'},
    {id:'social',label:'社交 / 关系',hue:335,color:'#cb789d',description:'约饭、约会、婚礼与拜访'},
    {id:'life',label:'生活事务',hue:205,color:'#8492a4',description:'购物、家务、手续和其他安排'},
  ];
  const byId = Object.fromEntries(families.map(f => [f.id,f]));
  const categories = {project:'work',research:'work',meeting:'work',interview:'work',talk:'work',travel:'entertainment',course:'growth',meal:'social',date:'social',club:'social',other:'life'};
  function family(event) {
    if (byId[event.category]) return byId[event.category];
    const title = event.title || '';
    // Older generic categories still gain meaningful colors without rewriting records.
    if (/论文|投稿|科研|TCAS|实验|工作|面试|组会|宣讲/i.test(title)) return byId.work;
    if (/体检|医院|就医|复诊|看病|按摩|健身|跑步|游泳|运动/.test(title)) return byId.health;
    if (/唱歌|演唱会|音乐会|电影|KTV|旅行|旅游|出游|自驾|娱乐/i.test(title)) return byId.entertainment;
    if (/约饭|吃饭|婚礼|拜访|聚会|约会|陪.*玩/.test(title)) return byId.social;
    if (/学习|读书|阅读|练习|课程|培训|考试/.test(title)) return byId.growth;
    return byId[categories[event.category] || 'life'];
  }
  function color(event) {
    const f=family(event);
    const hash=[...(event.id || event.title || '')].reduce((a,c) => (a*31+c.charCodeAt(0))>>>0,0);
    const hue=f.hue+(hash%17)-8, sat=f.id==='life' ? 18 : 43+(hash%10);
    return `hsl(${hue} ${sat}% ${53+((hash>>>4)%9)}%)`;
  }
  return {families,family,color};
})();
