/** Guest-First identity (web).
 * - device_id: localStorage (IP/와이파이 변경과 무관)
 * - Firebase Anonymous: FIREBASE_* 설정 시 선택 연동
 * - Kakao link: 공유/도감 저장 시 계정 병합
 */
(function (global) {
  const DEVICE_KEY = "jh_device_id";
  const UID_KEY = "jh_uid";
  const AUTH_TYPE_KEY = "jh_auth_type";

  function uuid() {
    if (crypto && crypto.randomUUID) return crypto.randomUUID().replace(/-/g, "");
    return `d${Date.now().toString(16)}${Math.random().toString(16).slice(2, 10)}`;
  }

  function getDeviceId() {
    let id = localStorage.getItem(DEVICE_KEY);
    if (!id) {
      id = uuid();
      localStorage.setItem(DEVICE_KEY, id);
    }
    return id;
  }

  function getUid() {
    return localStorage.getItem(UID_KEY) || "";
  }

  function setIdentity(uid, authType) {
    if (uid) localStorage.setItem(UID_KEY, uid);
    if (authType) localStorage.setItem(AUTH_TYPE_KEY, authType);
  }

  async function ensureGuest(api) {
    const device_id = getDeviceId();
    let firebase_uid = null;
    // Optional Firebase Anonymous (env injected later via meta/config)
    if (global.firebaseAuth && typeof global.firebaseAuth.signInAnonymously === "function") {
      try {
        const cred = await global.firebaseAuth.signInAnonymously();
        firebase_uid = cred?.user?.uid || null;
      } catch (err) {
        console.warn("firebase anonymous skipped", err);
      }
    }
    const data = await api("/v1/auth/guest", {
      method: "POST",
      body: JSON.stringify({ device_id, firebase_uid }),
    });
    setIdentity(data.uid, data.auth_type || "anonymous");
    return data;
  }

  async function linkKakao(api, accessToken) {
    const guest_uid = getUid();
    if (!guest_uid) throw new Error("guest missing");
    const data = await api("/v1/auth/kakao/link", {
      method: "POST",
      body: JSON.stringify({ guest_uid, access_token: accessToken }),
    });
    setIdentity(data.uid, "kakao");
    return data;
  }

  function authType() {
    return localStorage.getItem(AUTH_TYPE_KEY) || "anonymous";
  }

  function isLinked() {
    return authType() === "kakao";
  }

  global.JustHereAuth = {
    getDeviceId,
    getUid,
    ensureGuest,
    linkKakao,
    authType,
    isLinked,
    setIdentity,
  };
})(window);
