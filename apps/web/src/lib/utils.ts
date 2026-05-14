import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// Reverse Windows-1252 mojibake for emoji saved with the wrong encoding.
// Emoji UTF-8 bytes were interpreted as Win-1252 single bytes, then re-encoded
// as UTF-8 characters (e.g. "ðŸ—ï¸" instead of "🏗️").
const MOJIBAKE_MAP: [string, string][] = [
  ["ðŸ—ï¸", "🏗️"],  // 🏗️ building construction
  ["ðŸ› ï¸", "🛠️"],  // 🛠️ hammer and wrench
  ["ðŸ§ ",                   "🧠"],   // 🧠 brain
  ["ðŸŒ±",                   "🌱"],   // 🌱 seedling
  ["ðŸ‘‹",                   "👋"],   // 👋 waving hand
  ["ðŸ“Š",                   "📊"],   // 📊 bar chart
];

export function fixMojibake(text: string): string {
  let result = text;
  for (const [bad, good] of MOJIBAKE_MAP) {
    result = result.split(bad).join(good);
  }
  return result;
}
