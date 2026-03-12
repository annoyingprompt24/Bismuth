import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Bismuth — AI Development Pipeline',
  description: 'Recursive AI-driven development with the Bismuth methodology',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
      </head>
      <body className="bg-bismuth-bg text-bismuth-text font-sans antialiased">
        {children}
      </body>
    </html>
  )
}
