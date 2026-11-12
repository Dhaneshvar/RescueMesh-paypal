import { useEffect, useRef, useState } from 'react'
import { api } from './api'

const CLIENT_ID = import.meta.env.VITE_PAYPAL_CLIENT_ID
const CURRENCY = (import.meta.env.VITE_PAYPAL_CURRENCY || 'USD').toUpperCase()

export default function PayPalAuthorize({ mission, onChange }) {
  const [message, setMessage] = useState('')
  const [ready, setReady] = useState(false)
  const buttonRef = useRef(null)
  const sessionRef = useRef(null)

  useEffect(() => {
    if (!CLIENT_ID || mission?.payment?.state === 'authorized' || mission?.payment?.state === 'captured') return
    let mounted = true
    const load = () => new Promise((resolve, reject) => {
      if (window.paypal) return resolve()
      const script = document.createElement('script')
      script.async = true
      script.src = 'https://www.sandbox.paypal.com/web-sdk/v6/core'
      script.onload = resolve
      script.onerror = reject
      document.head.appendChild(script)
    })
    async function init() {
      try {
        await load()
        const sdk = await window.paypal.createInstance({ clientId: CLIENT_ID, components: ['paypal-payments'], pageType: 'checkout' })
        const methods = await sdk.findEligibleMethods({ currencyCode: CURRENCY })
        if (!methods.isEligible('paypal') || !mounted) return setMessage('PayPal is not eligible for this Sandbox buyer.')
        const session = sdk.createPayPalOneTimePaymentSession({
          onApprove: async (data) => {
            const payment = await api(`/api/missions/${mission.id}/paypal/authorize`, { method: 'POST', body: JSON.stringify({ order_id: data.orderId }) })
            onChange(payment)
            setMessage('Payment authorized. Capture it only after fulfilment verification.')
          },
          onCancel: () => setMessage('Payment approval was cancelled.'),
          onError: () => setMessage('PayPal could not process this payment. Try a different Sandbox funding source.'),
        })
        sessionRef.current = session
        if (mounted) setReady(true)
      } catch { setMessage('Could not initialize the PayPal Sandbox SDK.') }
    }
    init()
    return () => { mounted = false }
  }, [mission?.id, mission?.payment?.state, onChange])

  async function start() {
    try {
      if (!sessionRef.current) {
        setMessage('PayPal is still loading. Please wait a moment and try again.')
        return
      }
      setMessage('Creating a server-validated PayPal authorization…')
      const order = await api(`/api/missions/${mission.id}/paypal/order`, { method: 'POST' })
      if (order.demo) {
        const payment = await api(`/api/missions/${mission.id}/paypal/authorize`, { method: 'POST', body: JSON.stringify({ order_id: order.orderId }) })
        onChange(payment); setMessage('Demo authorization recorded. Add Sandbox credentials to use PayPal checkout.'); return
      }
      await sessionRef.current.start({ presentationMode: 'auto' }, Promise.resolve({ orderId: order.orderId }))
    } catch (error) { setMessage(error.message) }
  }

  if (!mission?.allocations?.some((x) => x.kind === 'paid_gap')) return null
  if (mission.payment?.state === 'authorized') return <p className="status authorized">Authorized — awaiting verification.</p>
  if (mission.payment?.state === 'captured') return <p className="status captured">Captured after verification.</p>
  return <div className="payment"><button ref={buttonRef} className="paypal" disabled={!ready} onClick={start}>{ready ? 'Authorize PayPal payment' : 'Loading PayPal…'}</button><p className="muted">{CURRENCY} {mission.allocations.filter(x => x.kind === 'paid_gap').reduce((s, x) => s + Number(x.cost), 0).toFixed(2)} · capture after verification</p>{message && <p className="message">{message}</p>}</div>
}

