import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AllCommunityModule } from 'ag-grid-community'
import { AgGridProvider } from 'ag-grid-react'
import './styles.css'
import './theme.css'
import './paypal-theme.css'
import App from './App'

const agGridModules = [AllCommunityModule]

createRoot(document.getElementById('root')).render(<StrictMode><AgGridProvider modules={agGridModules}><App /></AgGridProvider></StrictMode>)

