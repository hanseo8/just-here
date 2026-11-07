/* MY navigation only opens presentation folds; it never changes participation eligibility. */
(function(){
  function open(id){
    const target=document.getElementById(id);if(!target||target.hidden)return false;
    if(target.tagName==='DETAILS')target.open=true;
    for(let parent=target.parentElement;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;
    target.scrollIntoView({behavior:'smooth',block:'start'});return true;
  }
  function renderTitles(rows){
    const list=document.getElementById('my-title-list');list.replaceChildren();
    const latest=rows[rows.length-1];const image=document.getElementById('my-title-image');
    document.getElementById('my-title-name').textContent=latest?.title||'첫 칭호를 만나볼까요?';
    document.getElementById('my-title-description').textContent=latest?.sub_text||'가게를 고르면 나의 음식 취향 칭호가 쌓여요.';
    document.getElementById('my-title-count').textContent=rows.length?'모은 칭호 '+rows.length+'개':'아직 받은 칭호가 없어요';
    document.getElementById('my-title-collection').hidden=!rows.length;
    image.hidden=true;image.removeAttribute('src');
    if(latest?.id&&/^[a-z_]+$/.test(latest.id)){image.src='/static/badges/'+latest.id+'.png?v=20260930-badges1';image.hidden=false;image.onerror=()=>{image.hidden=true;};}
    for(const row of rows){const card=document.createElement('div');card.className='my-title-chip';const name=document.createElement('strong');name.textContent=row.title;card.append(name);list.append(card);}
  }
  window.JustHereMy={open,renderTitles};
  window.addEventListener('hashchange',()=>open(location.hash.slice(1)));
  window.addEventListener('DOMContentLoaded',()=>{if(location.hash)open(location.hash.slice(1));});
})();
