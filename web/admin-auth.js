/* Sessions stay in memory; credentials never enter URLs or browser storage. */
window.JustHereAdminAuth = (() => {
  let session = '', owner = '', expires = 0;
  async function ensure(token, otp = '') {
    if (owner === token && Date.now() < expires) return;
    session = ''; owner = ''; expires = 0;
    const response = await fetch('/v1/admin/auth', {
      method: 'POST', cache: 'no-store',
      headers: {'Content-Type': 'application/json', 'X-Admin-Token': token},
      body: JSON.stringify({otp})
    });
    if (!response.ok) throw new Error('관리자 토큰과 인증 앱의 새 6자리 번호를 확인해 주세요.');
    const data = await response.json();
    session = data.session_token || ''; owner = token;
    expires = Date.now() + (data.two_factor_required ? data.expires_in * 1000 - 5000 : 600000);
    const input = document.getElementById('otp');
    if (input) input.value = '';
  }
  function headers(token) {
    return {'X-Admin-Token': token, ...(owner === token && session ? {'X-Admin-Session': session} : {})};
  }
  return {ensure, headers};
})();
