import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ludwig",
  description: "Prompt to editable 3D model — local-first.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="container">
          <header className="site">
            <h1>Ludwig</h1>
            <nav>
              <Link href="/">Generate</Link>
              <Link href="/projects">Projects</Link>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
