import { AgGridReact } from 'ag-grid-react'
import 'ag-grid-community/styles/ag-grid.css'
import 'ag-grid-community/styles/ag-theme-quartz.css'

export default function LedgerGrid({ rows = [] }) {
  const columnDefs = [
    { field: 'status', headerName: 'Status', flex: 1, filter: true },
    { field: 'amount', headerName: 'Amount', flex: 1 },
    { field: 'currency', headerName: 'Currency', flex: 1 },
    { field: 'destination', headerName: 'Destination', flex: 2 },
    { field: 'mission_id', headerName: 'Mission', flex: 2 },
    { field: 'capture_id', headerName: 'PayPal capture', flex: 2 },
    { field: 'created_at', headerName: 'Recorded at', flex: 2 }
  ]
  const data = rows.filter((row) => row.kind === 'payment').map((row) => ({ ...row, destination: (row.destination || []).join(', ') }))
  return <div className="ag-theme-quartz ledger-grid"><AgGridReact rowData={data} columnDefs={columnDefs} domLayout="autoHeight" pagination paginationPageSize={5} animateRows /></div>
}
