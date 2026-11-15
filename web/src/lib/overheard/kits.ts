// Sample brand kit content for the demo. Not official brand material.
export interface BrandKit {
  voice: string[];
  use: string[];
  avoid: string[];
  facts: { label: string; value: string }[];
  files: { name: string; type: string; updated: string }[];
  colors: { name: string; hex: string }[];
  emoji: { e: string; use: string }[];
}

const files = (brand: string, manual: string) => [
  { name: `${brand} brand voice guide`, type: "PDF", updated: "Oct 2026" },
  { name: manual, type: "PDF", updated: "Sep 2026" },
  { name: `${brand} customer FAQ`, type: "Doc", updated: "Nov 2026" },
];

export const KITS: Record<string, BrandKit> = {
  nespresso: {
    voice: ["Warm and refined, never salesy", "Talk about the coffee moment, not the machine", "Use first names when you can"],
    use: ["ritual", "crafted", "we would love to help"],
    avoid: ["pods", "cheap", "unfortunately"],
    facts: [
      { label: "Warranty", value: "2 years on machines" },
      { label: "Descaling", value: "Every 3 months or 600 capsules" },
      { label: "Recycling", value: "Free capsule recycling bags with every order" },
      { label: "Office orders", value: "Handled by Nespresso Professional" },
    ],
    colors: [{ name: "Black", hex: "#000000" }, { name: "Gold", hex: "#C8A165" }, { name: "Cream", hex: "#F3EDE4" }],
    emoji: [{ e: "☕", use: "Coffee moments" }, { e: "🤎", use: "Thank you sign off" }, { e: "✨", use: "New launches" }],
    files: files("Nespresso", "Vertuo machine manual"),
  },
  traeger: {
    voice: ["Friendly and a little playful", "Celebrate the cook and the crowd", "Short sentences, plenty of energy"],
    use: ["wood fired", "flavor", "Traegerhood"],
    avoid: ["grill brand", "propane", "just"],
    facts: [
      { label: "Warranty", value: "3 years on grills" },
      { label: "Pellets", value: "Use Traeger hardwood pellets only" },
      { label: "Common fix", value: "Clean the firepot before every long cook" },
    ],
    colors: [{ name: "Traeger Black", hex: "#1A1A1A" }, { name: "Ember Orange", hex: "#E35205" }, { name: "Smoke Grey", hex: "#8C8C8C" }],
    emoji: [{ e: "🔥", use: "Great cooks" }, { e: "🍗", use: "Food wins" }, { e: "🙌", use: "Celebrating fans" }],
    files: files("Traeger", "Ironwood owner's manual"),
  },
  breville: {
    voice: ["Expert but approachable", "Explain the why in one line", "Calm and precise"],
    use: ["barista quality", "dial in", "here is a quick tip"],
    avoid: ["broken", "user error", "obviously"],
    facts: [
      { label: "Warranty", value: "1 to 2 years depending on model" },
      { label: "Descaling", value: "Check the tank is fully seated before starting" },
      { label: "Support", value: "breville.com/support" },
    ],
    colors: [{ name: "Brushed Steel", hex: "#A7A9AC" }, { name: "Charcoal", hex: "#333333" }, { name: "Breville Red", hex: "#C8102E" }],
    emoji: [{ e: "☕", use: "Coffee wins" }, { e: "👌", use: "Nailed it" }, { e: "💡", use: "Quick tips" }],
    files: files("Breville", "Barista Express manual"),
  },
  caraway: {
    voice: ["Bright, kind and design minded", "Lead with care, then the fix", "Emoji are fine, one at most"],
    use: ["non toxic", "ceramic", "your kitchen"],
    avoid: ["Teflon", "chemicals", "cheap"],
    facts: [
      { label: "Coating", value: "1 year warranty on the ceramic coating" },
      { label: "Returns", value: "30 day trial" },
      { label: "Care", value: "Low to medium heat, hand wash only" },
    ],
    colors: [{ name: "Sage", hex: "#9CAF88" }, { name: "Marigold", hex: "#E8A33D" }, { name: "Cream", hex: "#F4EDE1" }, { name: "Navy", hex: "#2B3A55" }],
    emoji: [{ e: "💛", use: "Thank you sign off" }, { e: "🍳", use: "Cooking wins" }, { e: "🌿", use: "Non toxic talk" }],
    files: files("Caraway", "Cookware care guide"),
  },
  ninja: {
    voice: ["Upbeat and direct", "Show what it can do with a quick idea", "Keep it under two sentences"],
    use: ["game changer", "try this", "program"],
    avoid: ["complicated", "can't", "sorry for the inconvenience"],
    facts: [
      { label: "Warranty", value: "1 year limited" },
      { label: "Creami tip", value: "Freeze pints flat for 24 hours" },
      { label: "Support", value: "ninjakitchen.com/support" },
    ],
    colors: [{ name: "Ninja Black", hex: "#111111" }, { name: "Ninja Green", hex: "#6CC24A" }, { name: "Silver", hex: "#C0C0C0" }],
    emoji: [{ e: "🥷", use: "Signature sign off" }, { e: "🍦", use: "Creami wins" }, { e: "💪", use: "Protein recipes" }],
    files: files("Ninja", "Creami owner's guide"),
  },
};
