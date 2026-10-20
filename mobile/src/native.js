import { Capacitor } from '@capacitor/core';
import { Geolocation } from '@capacitor/geolocation';
import { Browser } from '@capacitor/browser';
import { App } from '@capacitor/app';
import { Camera, CameraResultType, CameraSource } from '@capacitor/camera';

if (Capacitor.isNativePlatform()) {
  const base = 'https://justthis.co.kr';
  const originalFetch = window.fetch.bind(window);
  window.JustHereNative = {
    apiBase: base,
    remoteUrl: value => value?.startsWith('/v1/') ? base + value : value,
  };
  const originalOpen = window.open?.bind(window);
  window.open = (url, ...args) => {
    const target = new URL(url, location.href);
    if (target.protocol === 'https:' && target.origin !== location.origin) {
      Browser.open({url:target.href}).catch(() => window.alert('외부 페이지를 열지 못했어요.'));
      return {closed:false,focus:()=>{}};
    }
    return originalOpen?.(url, ...args);
  };
  window.fetch = (input, options = {}) => {
    const raw = typeof input === 'string' ? input : input.url || String(input);
    const local = new URL(raw, location.href);
    const api = local.origin === location.origin &&
      (local.pathname.startsWith('/v1/') || local.pathname === '/health');
    const target = api ? new URL(local.pathname + local.search, base).href : raw;
    const headers = new Headers(options.headers || (input instanceof Request ? input.headers : {}));
    if (['X-Guest-Token','X-Admin-Token','X-Merchant-Key'].some(key => headers.has(key)) &&
        new URL(target, location.href).origin !== base) {
      return Promise.reject(new Error('Credential destination blocked'));
    }
    if (api && input instanceof Request) return originalFetch(new Request(target, input), options);
    return originalFetch(target, options);
  };
  const nativeGeo = {
    getCurrentPosition(success, failure, options = {}) {
      Geolocation.getCurrentPosition(options).then(success).catch(failure || (() => {}));
    },
    watchPosition(success, failure, options = {}) {
      const pending = Geolocation.watchPosition(options, (position, error) => {
        if (error) failure?.(error); else if (position) success(position);
      });
      pending.catch(failure || (() => {}));
      return pending;
    },
    clearWatch(id) { Promise.resolve(id).then(id => Geolocation.clearWatch({id})).catch(() => {}); },
  };
  Object.defineProperty(navigator, 'geolocation', {value:nativeGeo, configurable:true});
  document.addEventListener('click', event => {
    const anchor = event.target.closest?.('a[href]');
    if (!anchor) return;
    const url = new URL(anchor.href, location.href);
    if (url.origin !== location.origin && url.protocol === 'https:') {
      event.preventDefault();
      Browser.open({url:url.href}).catch(() => window.alert('외부 페이지를 열지 못했어요. 잠시 후 다시 시도해 주세요.'));
    }
  });
  App.addListener('backButton', () => {
    if (location.pathname !== '/' && location.pathname !== '/index.html') location.href='/index.html';
    else if (history.length > 1) history.back();
    else App.minimizeApp();
  });
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('input[type="file"][accept*="image"]').forEach(input => {
      const button = document.createElement('button');
      button.type='button'; button.textContent='카메라로 촬영 · 사진 선택';
      button.onclick=async()=>{
        button.disabled=true;
        try {
          const photo=await Camera.getPhoto({quality:80,resultType:CameraResultType.Uri,source:CameraSource.Prompt,
            promptLabelHeader:'영수증 사진',promptLabelPhoto:'사진에서 선택',promptLabelPicture:'촬영하기'});
          const response=await originalFetch(photo.webPath);
          const blob=await response.blob();
          if(blob.size>8*1024*1024)throw Error('영수증은 8MB 이하로 선택해 주세요.');
          const transfer=new DataTransfer();
          transfer.items.add(new File([blob],'receipt.'+(photo.format||'jpeg'),{type:blob.type||'image/jpeg'}));
          input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));
        } catch(error) {
          if(!/cancel/i.test(String(error))) window.alert('사진을 선택하지 못했어요. 권한을 확인하거나 아래 파일 선택을 이용해 주세요.');
        } finally {button.disabled=false;}
      };
      input.after(button);
    });
  });
}
