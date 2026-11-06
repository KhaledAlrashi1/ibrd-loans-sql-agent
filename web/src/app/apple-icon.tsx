// Home-screen icon: icon.svg drawn full-bleed at 180 px (iOS rounds the corners itself).
import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "center", gap: 17, paddingLeft: 39, background: "#007d61" }}>
        {[101, 73, 45].map((w) => <div key={w} style={{ width: w, height: 17, borderRadius: 9, background: "#fdfcf9" }} />)}
      </div>
    ),
    size,
  );
}
