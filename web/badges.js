(function (global) {
  const THEME_TO_PERSONA = {
    bg_destiny: "first_love",
    bg_ironwall: "picky_king",
    bg_sprint: "no_hesitation",
    bg_overthink: "decision_paralysis",
    bg_meat: "meat_myway",
    bg_herb: "herbivore",
    bg_chameleon: "chameleon",
    bg_survival: "storm_survivor",
    bg_midnight: "night_hyena",
    bg_nomad: "food_nomad",
    bg_heat: "heat_explorer",
    bg_morning: "morning_hunter",
    bg_hermit: "weekend_hermit",
    bg_spicy: "spicy_ranker",
    bg_temp: "temp_guardian",
    bg_flex: "flexer",
    bg_value: "value_hunter",
    bg_carb: "carb_addict",
    bg_hangover: "hangover_god",
    bg_basic: "instinct_master",
  };

  function resolve(personaId, assetId) {
    const clean = String(personaId || "").trim();
    return clean || THEME_TO_PERSONA[assetId] || "instinct_master";
  }

  function url(personaId, assetId) {
    return `/static/badges/${resolve(personaId, assetId)}.png?v=20260930-badges1`;
  }

  function load(personaId, assetId) {
    return new Promise((resolveImage) => {
      const image = new Image();
      image.onload = () => resolveImage(image);
      image.onerror = () => resolveImage(null);
      image.src = url(personaId, assetId);
    });
  }

  global.JustHereBadges = { resolve, url, load };
})(window);
