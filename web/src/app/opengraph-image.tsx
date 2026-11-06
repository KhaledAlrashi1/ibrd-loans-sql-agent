// Link preview (Open Graph): see src/og/card.tsx.
import { OG_ALT, OG_SIZE, renderCard } from "@/og/card";

export const alt = OG_ALT;
export const size = OG_SIZE;
export const contentType = "image/png";

export default function Image() {
  return renderCard();
}
