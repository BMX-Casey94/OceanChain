import type { Metadata, Viewport } from 'next'
import { Inter, Bebas_Neue } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import './globals.css'

const inter = Inter({ 
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
})

const bebasNeue = Bebas_Neue({ 
  weight: "400",
  subsets: ["latin"],
  variable: "--font-bebas-neue",
  display: "swap",
})

export const metadata: Metadata = {
  title: 'OceanChain | BSV Maritime Intelligence',
  description: 'OceanChain permanently records global maritime AIS data on the BSV blockchain — creating an immutable, publicly verifiable record of the world\'s oceans.',
  generator: 'Next.js',
  keywords: ['BSV', 'blockchain', 'maritime', 'AIS', 'vessel tracking', 'ocean', 'shipping'],
  authors: [{ name: 'OceanChain' }],
  openGraph: {
    title: 'OceanChain | BSV Maritime Intelligence',
    description: 'Every vessel. Every coordinate. Every moment. Permanent blockchain records of global maritime data.',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'OceanChain | BSV Maritime Intelligence',
    description: 'Every vessel. Every coordinate. Every moment. Permanent blockchain records of global maritime data.',
  },
}

export const viewport: Viewport = {
  themeColor: '#000d14',
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning style={{ colorScheme: 'dark' }}>
      <body className={`${inter.variable} ${bebasNeue.variable} font-sans antialiased`}>
        {children}
        <Analytics />
      </body>
    </html>
  )
}
