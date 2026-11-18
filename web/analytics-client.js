/* Attribution labels only: never store a URL, referrer, coordinates or auth token. */
(function () {
  const fields = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content'];
  const key = 'jh_analytics_visit_v1';
  const ttl = 30 * 60 * 1000;
  const slug = value => typeof value === 'string' && /^[a-zA-Z0-9_-]{1,80}$/.test(value) ? value : '';
  let memory;
  function context() {
    const params = new URLSearchParams(location.search);
    const labels = {};
    for (const name of fields) { const value=slug(params.get(name)); if(value) labels[name]=value; }
    const test = (!window.JustHereNative && ['localhost','127.0.0.1','::1','[::1]'].includes(location.hostname)) || params.get('analytics_test') === '1';
    if (test || params.has('design')) return {traffic_type:'test'};
    const now = Date.now();
    let old=memory;
    try { old=JSON.parse(sessionStorage.getItem(key)||'null') || memory; } catch (_) {}
    const explicit = Object.keys(labels).length > 0;
    const oldLabels = {};
    for(const name of fields) { const value=slug(old?.[name]); if(value) oldLabels[name]=value; }
    const valid = old && /^[a-zA-Z0-9_-]{16,80}$/.test(old.visit_id||'') && Number.isFinite(old.updated_at) && now>=old.updated_at && now-old.updated_at<ttl;
    const changed = explicit && fields.some(name=>(labels[name]||'')!==(oldLabels[name]||''));
    const id = valid&&!changed ? old.visit_id : crypto.randomUUID();
    const current={visit_id:id,...(explicit?labels:valid?oldLabels:{})};
    memory={...current,updated_at:now};
    try { sessionStorage.setItem(key,JSON.stringify(memory)); } catch (_) {}
    return {...current};
  }
  window.JustHereAnalytics = {context};
})();
