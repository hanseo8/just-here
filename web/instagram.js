/* Curated, branch-specific Instagram posts. No scraping or copied media. */
(function (global) {
  let catalog;
  let embedScript;
  function postUrl(value) {
    try {
      const u = new URL(value);
      if (u.protocol !== "https:" || u.hostname !== "www.instagram.com") return null;
      if (!/^\/(p|reel)\/[A-Za-z0-9_-]+\/$/.test(u.pathname)) return null;
      return u.origin + u.pathname;
    } catch (_) { return null; }
  }
  function loadScript() {
    if (global.instgrm?.Embeds) return Promise.resolve();
    if (embedScript) return embedScript;
    embedScript = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://www.instagram.com/embed.js";
      script.async = true;
      const timeout = setTimeout(() => { script.remove(); reject(new Error("timeout")); }, 12000);
      script.onload = () => {
        clearTimeout(timeout);
        global.instgrm?.Embeds ? resolve() : reject(new Error("unavailable"));
      };
      script.onerror = () => { clearTimeout(timeout); script.remove(); reject(new Error("network")); };
      document.head.append(script);
    }).catch((error) => { embedScript = null; throw error; });
    return embedScript;
  }
  function link(label, href) {
    const a = document.createElement("a");
    a.textContent = label;
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    return a;
  }
  async function mount(root, card) {
    const marker = {};
    root.instagramMarker = marker;
    try {
      if (!catalog) catalog = fetch("/static/instagram-places.json")
        .then((r) => { if (!r.ok) throw new Error("catalog"); return r.json(); })
        .catch((e) => { catalog = null; throw e; });
      const entries = await catalog;
      if (!root.isConnected || root.instagramMarker !== marker) return;
      const entry = entries.find((e) => e.branch_verified === true &&
        e.place_id === card.place_id && /^\w[\w.]{0,29}$/.test(e.username));
      if (!entry || card.is_brand) return;
      const section = document.createElement("section");
      section.className = "instagram-detail";
      const title = document.createElement("h3");
      title.textContent = "음식·가게 분위기";
      section.append(title, link("@" + entry.username + " · 인스타그램에서 보기", "https://www.instagram.com/" + entry.username + "/"));
      const posts = (entry.posts || []).map(postUrl).filter(Boolean).slice(0, 3);
      if (posts.length) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn ghost";
        button.textContent = "게시물 보기";
        const status = document.createElement("p");
        status.setAttribute("role", "status");
        status.textContent = "누르면 Instagram 콘텐츠를 불러옵니다.";
        const content = document.createElement("div");
        button.onclick = async (event) => {
          event.stopPropagation();
          button.disabled = true;
          content.replaceChildren();
          posts.forEach((url, i) => {
            content.append(link("게시물 " + (i + 1) + " 원문 보기", url));
            const quote = document.createElement("blockquote");
            quote.className = "instagram-media";
            quote.dataset.instgrmPermalink = url;
            quote.append(link("Instagram에서 게시물 보기", url));
            content.append(quote);
          });
          status.textContent = "게시물을 불러오는 중이에요…";
          try {
            await loadScript();
            if (!section.isConnected || root.instagramMarker !== marker) return;
            global.instgrm.Embeds.process();
            status.textContent = "게시물이 표시되지 않으면 원문 보기를 눌러 주세요.";
            button.hidden = true;
          } catch (_) {
            if (!section.isConnected || root.instagramMarker !== marker) return;
            status.textContent = "게시물을 불러오지 못했어요. 원문으로 확인할 수 있어요.";
            button.textContent = "다시 불러오기";
            button.disabled = false;
          }
        };
        section.append(button, status, content);
      }
      root.append(section);
    } catch (_) { /* Restaurant details remain usable when the optional catalog fails. */ }
  }
  global.JustHereInstagram = { mount };
})(window);
