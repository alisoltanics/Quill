import Head from 'next/head'
import dynamic from 'next/dynamic'

const Chat = dynamic(() => import('../components/Chat'), { ssr: false })

export default function Home() {
  return (
    <div>
      <Head>
        <title>Realtime Gateway — Frontend</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>
      <main style={{ maxWidth: 800, margin: '2rem auto', padding: '1rem' }}>
        <h1>Realtime Gateway — Collaborative Document UI</h1>
        <p>Connects to the gateway via WebSocket and shows realtime document updates.</p>
        <Chat />
      </main>
    </div>
  )
}
