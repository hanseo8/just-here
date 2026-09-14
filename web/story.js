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
    bg_destiny: ["#FF6B6B", "#FF8E8B", "#1a120e"],
    bg_ironwall: ["#4A4A4A", "#2C3E50", "#ffffff"],
    bg_sprint: ["#00E676", "#1DE9B6", "#0b2e1c"],
    bg_overthink: ["#5C6BC0", "#283593", "#ffffff"],
    bg_meat: ["#F44336", "#BF360C", "#ffffff"],
    bg_herb: ["#66BB6A", "#1B5E20", "#ffffff"],
    bg_chameleon: ["#AB47BC", "#6A1B9A", "#ffffff"],
    bg_survival: ["#34495E", "#5D6D7E", "#ffffff"],
    bg_midnight: ["#1A1A2E", "#E94560", "#ffffff"],
    bg_nomad: ["#D4A373", "#FAEDCD", "#3b2a1a"],
    bg_heat: ["#FF7043", "#E65100", "#2a1000"],
    bg_morning: ["#FFCC80", "#FF8A65", "#3b2410"],
    bg_hermit: ["#90A4AE", "#455A64", "#ffffff"],
    bg_spicy: ["#D32F2F", "#FF0000", "#ffffff"],
    bg_temp: ["#FF5A00", "#FF9B00", "#2a1200"],
    bg_flex: ["#FFD700", "#F1C40F", "#2a2200"],
    bg_value: ["#26A69A", "#004D40", "#ffffff"],
    bg_carb: ["#FFB74D", "#EF6C00", "#2a1600"],
    bg_hangover: ["#4DB6AC", "#00695C", "#ffffff"],
    bg_basic: ["#FF5A00", "#E62E00", "#ffffff"],
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
  function layoutBody(ctx, receipt, ink, startY, paint) {
    let y = startY;

    ctx.textAlign = "center";
    ctx.font = '600 28px "IBM Plex Sans KR", sans-serif';
    if (paint) {
      ctx.fillStyle = withAlpha(ink, 0.75);
      ctx.fillText("JUST HERE · 식탐 영수증", W / 2, y);
    }
    y += 90;

    ctx.font = "120px sans-serif";
    if (paint) {
      ctx.fillStyle = ink;
      ctx.fillText(receipt.sticker || "🍚", W / 2, y + 40);
    }
    y += 150;

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
    const bodyEnd = layoutBody(ctx, receipt, ink, SAFE_TOP, false);
    const bodyHeight = bodyEnd - SAFE_TOP;
    const room = SAFE_BOTTOM - 140 - SAFE_TOP;
    const offset = Math.max(0, (room - bodyHeight) / 2);
    layoutBody(ctx, receipt, ink, SAFE_TOP + offset, true);

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
