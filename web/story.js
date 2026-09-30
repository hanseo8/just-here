/* 인스타 스토리용 영수증 이미지(1080x1920) 생성.
   보상 루프("스토리에 올리고 태그하면 골드")가 성립하려면
   사용자 손에 올릴 이미지가 먼저 있어야 한다. */
(function (global) {
  const W = 1080;
  const H = 1920;
  // 스토리 상·하단은 인스타 UI가 덮는다
  const SAFE_TOP = 330;
  const SAFE_BOTTOM = 1640;
  const PAD = 96;

  const HANDLE = "@official.just.this";
  const SITE = "justthis.co.kr";

  // styles.css의 .receipt-card.theme-* 와 같은 값을 유지한다
  const THEMES = {
    bg_destiny: ["#ff7a3d", "#ff5a1f", "#fbfdfb"],
    bg_ironwall: ["#183d2d", "#205c3c", "#fbfdfb"],
    bg_sprint: ["#39a66b", "#248552", "#fbfdfb"],
    bg_overthink: ["#205c3c", "#ff5a1f", "#fbfdfb"],
    bg_meat: ["#e94e1b", "#ff7a3d", "#fbfdfb"],
    bg_herb: ["#318e5b", "#205c3c", "#fbfdfb"],
    bg_chameleon: ["#205c3c", "#ff5a1f", "#fbfdfb"],
    bg_survival: ["#183d2d", "#2f6f4c", "#fbfdfb"],
    bg_midnight: ["#183d2d", "#ff5a1f", "#fbfdfb"],
    bg_nomad: ["#e4f3e9", "#fff0e5", "#183d2d"],
    bg_heat: ["#ff7a3d", "#e94e1b", "#fbfdfb"],
    bg_morning: ["#fff0e5", "#ffd7bf", "#183d2d"],
    bg_hermit: ["#577360", "#205c3c", "#fbfdfb"],
    bg_spicy: ["#ff5a1f", "#d94312", "#fbfdfb"],
    bg_temp: ["#ff8a3d", "#ff5a1f", "#fbfdfb"],
    bg_flex: ["#ffb23f", "#ff7a3d", "#183d2d"],
    bg_value: ["#248552", "#183d2d", "#fbfdfb"],
    bg_carb: ["#ffd19f", "#ff8a3d", "#183d2d"],
    bg_hangover: ["#39a66b", "#205c3c", "#fbfdfb"],
    bg_basic: ["#205c3c", "#ff5a1f", "#fbfdfb"],
  };

  function theme(id) {
    return THEMES[id] || THEMES.bg_basic;
  }

  function withAlpha(hex, alpha) {
    const n = parseInt(hex.replace("#", ""), 16);
    const r = (n >> 16) & 255;
    const g = (n >> 8) & 255;
    const b = n & 255;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  async function loadFonts() {
    if (!global.document?.fonts) return;
    try {
      await Promise.all([
        document.fonts.load('700 64px "IBM Plex Sans KR"'),
        document.fonts.load('500 36px "IBM Plex Sans KR"'),
        document.fonts.load('400 76px "Black Han Sans"'),
      ]);
      await document.fonts.ready;
    } catch (_) {}
  }

  /** 주어진 폭에 맞춰 줄바꿈한 줄 배열 */
  function wrap(ctx, text, maxWidth) {
    const words = String(text || "").split(/\s+/).filter(Boolean);
    if (!words.length) return [];
    const lines = [];
    let line = words[0];
    for (let i = 1; i < words.length; i++) {
      const next = `${line} ${words[i]}`;
      if (ctx.measureText(next).width > maxWidth) {
        lines.push(line);
        line = words[i];
      } else {
        line = next;
      }
    }
    lines.push(line);
    return lines;
  }

  /** 한 줄이 넘치면 말줄임 */
  function ellipsize(ctx, text, maxWidth) {
    let s = String(text || "");
    if (ctx.measureText(s).width <= maxWidth) return s;
    while (s.length > 1 && ctx.measureText(s + "…").width > maxWidth) {
      s = s.slice(0, -1);
    }
    return s + "…";
  }

  function drawRow(ctx, label, value, y, ink, maxWidth, paint) {
    ctx.font = '500 34px "IBM Plex Sans KR", sans-serif';
    if (paint) {
      ctx.textAlign = "left";
      ctx.fillStyle = withAlpha(ink, 0.72);
      ctx.fillText(label, PAD, y);
    }

    ctx.font = '600 36px "IBM Plex Sans KR", sans-serif';
    if (paint) {
      ctx.textAlign = "right";
      ctx.fillStyle = ink;
      ctx.fillText(ellipsize(ctx, value, maxWidth - 180), W - PAD, y);
    }
  }

  /**
   * 본문을 그리거나(paint=true) 높이만 잰다(paint=false).
   * 두 번 돌려서 위아래 여백을 같게 맞춘다 — 스토리에서 아래가 뜨면 허전해 보인다.
   * @returns {number} 마지막으로 쓴 y
   */
  function layoutBody(ctx, receipt, ink, startY, paint, badgeImage) {
    let y = startY;

    ctx.textAlign = "center";
    ctx.font = '600 28px "IBM Plex Sans KR", sans-serif';
    if (paint) {
      ctx.fillStyle = withAlpha(ink, 0.75);
      ctx.fillText("JUST HERE · 식탐 영수증", W / 2, y);
    }
    y += 90;

    const badgeSize = 300;
    if (paint && badgeImage) {
      ctx.drawImage(badgeImage, (W - badgeSize) / 2, y - 24, badgeSize, badgeSize);
    }
    y += badgeSize + 24;

    ctx.font = '400 76px "Black Han Sans", "IBM Plex Sans KR", sans-serif';
    wrap(ctx, receipt.title || "오늘의 선택", W - PAD * 2).forEach((line) => {
      y += 88;
      if (paint) {
        ctx.fillStyle = ink;
        ctx.fillText(line, W / 2, y);
      }
    });

    if (receipt.sub_text) {
      ctx.font = '400 36px "IBM Plex Sans KR", sans-serif';
      y += 26;
      wrap(ctx, receipt.sub_text, W - PAD * 2).slice(0, 3).forEach((line) => {
        y += 52;
        if (paint) {
          ctx.fillStyle = withAlpha(ink, 0.92);
          ctx.fillText(line, W / 2, y);
        }
      });
    }

    y += 76;
    if (paint) {
      ctx.strokeStyle = withAlpha(ink, 0.28);
      ctx.lineWidth = 2;
      ctx.setLineDash([10, 10]);
      ctx.beginPath();
      ctx.moveTo(PAD, y);
      ctx.lineTo(W - PAD, y);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    const rowWidth = W - PAD * 2;
    y += 74;
    drawRow(ctx, "식당", receipt.place_name || "-", y, ink, rowWidth, paint);
    y += 66;
    const mode = receipt.intent === "delivery" ? "배달" : "방문";
    drawRow(ctx, "메뉴", `${receipt.menu_name || "-"} · ${mode}`, y, ink, rowWidth, paint);
    if (receipt.match_reason) {
      y += 66;
      drawRow(ctx, "한 줄", receipt.match_reason, y, ink, rowWidth, paint);
    }

    return y;
  }

  /**
   * 영수증 데이터를 1080x1920 캔버스로 그린다.
   * @returns {Promise<HTMLCanvasElement>}
   */
  async function renderStoryCanvas(receipt = {}, opts = {}) {
    await loadFonts();

    const [c1, c2, inkRaw] = theme(receipt.asset_id || receipt.theme);
    const ink = inkRaw;
    const gold = !!opts.gold;
    const badgeImage = await global.JustHereBadges?.load(
      receipt.persona_id,
      receipt.asset_id || receipt.theme
    );

    const canvas = document.createElement("canvas");
    canvas.width = W;
    canvas.height = H;
    const ctx = canvas.getContext("2d");

    const grad = ctx.createLinearGradient(0, 0, W * 0.45, H);
    grad.addColorStop(0, c1);
    grad.addColorStop(1, c2);
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);

    if (gold) {
      ctx.strokeStyle = "#d9a62e";
      ctx.lineWidth = 10;
      ctx.strokeRect(28, 28, W - 56, H - 56);
    }

    // 본문 높이를 먼저 재고, 안전 영역 안에서 세로 중앙에 앉힌다
    const bodyEnd = layoutBody(ctx, receipt, ink, SAFE_TOP, false, badgeImage);
    const bodyHeight = bodyEnd - SAFE_TOP;
    const room = SAFE_BOTTOM - 140 - SAFE_TOP;
    const offset = Math.max(0, (room - bodyHeight) / 2);
    layoutBody(ctx, receipt, ink, SAFE_TOP + offset, true, badgeImage);

    // 하단 고정: 보는 사람이 어디로 가야 하는지
    ctx.textAlign = "center";
    ctx.font = '700 44px "IBM Plex Sans KR", sans-serif';
    ctx.fillStyle = ink;
    ctx.fillText(SITE, W / 2, SAFE_BOTTOM - 60);

    ctx.font = '500 32px "IBM Plex Sans KR", sans-serif';
    ctx.fillStyle = withAlpha(ink, 0.78);
    ctx.fillText(HANDLE, W / 2, SAFE_BOTTOM);

    return canvas;
  }

  function toBlob(canvas) {
    return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  }

  /**
   * 이미지를 만들어 공유 시트로 넘긴다. 공유가 안 되면 저장으로 떨어진다.
   * @returns {Promise<"shared"|"saved"|"opened"|"cancelled"|"failed">}
   */
  async function shareStoryImage(receipt, opts = {}) {
    let blob;
    try {
      const canvas = await renderStoryCanvas(receipt, opts);
      blob = await toBlob(canvas);
    } catch (err) {
      console.error(err);
      return "failed";
    }
    if (!blob) return "failed";

    const file = new File([blob], "justhere-receipt.png", { type: "image/png" });

    if (navigator.canShare?.({ files: [file] })) {
      try {
        await navigator.share({ files: [file] });
        return "shared";
      } catch (err) {
        if (err?.name === "AbortError") return "cancelled";
      }
    }

    const url = URL.createObjectURL(blob);
    try {
      const a = document.createElement("a");
      if ("download" in a) {
        a.href = url;
        a.download = "justhere-receipt.png";
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 10000);
        return "saved";
      }
      // iOS 구버전: 새 탭에서 길게 눌러 저장
      window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      return "opened";
    } catch (err) {
      console.error(err);
      URL.revokeObjectURL(url);
      return "failed";
    }
  }

  global.JustHereStory = { renderStoryCanvas, shareStoryImage };
})(window);
