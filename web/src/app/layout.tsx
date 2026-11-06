import type { Metadata, Viewport } from "next";
import { Source_Sans_3, Source_Serif_4 } from "next/font/google";
import "./globals.css";

// Self-hosted at build time by next/font: the browser never calls Google.
const sans = Source_Sans_3({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const serif = Source_Serif_4({ subsets: ["latin"], variable: "--font-serif", display: "swap" });

const TITLE = "Ask the IBRD loan book";
const DESCRIPTION = "Ask about IBRD loans in plain English and see the answer, its SQL and every assumption.";
// Absolute URLs for the preview images: production on production, the deployment's own URL on a preview.
const SITE_URL = process.env.VERCEL_ENV === "production" ? "https://ibrd-loans-sql-agent.vercel.app"
  : process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : "http://localhost:3000";

// The preview images come from opengraph-image.tsx / twitter-image.tsx; the icons from icon.svg,
// apple-icon.tsx and favicon.ico.
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: TITLE,
  description: DESCRIPTION,
  openGraph: { type: "website", url: "/", siteName: TITLE, title: TITLE, description: DESCRIPTION, locale: "en_US" },
  twitter: { card: "summary_large_image", title: TITLE, description: DESCRIPTION },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f8f7f3" },
    { media: "(prefers-color-scheme: dark)", color: "#121211" },
  ],
};

// Applies a stored theme before the first paint (no flash). Without one, CSS follows the OS.
const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}})()`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
