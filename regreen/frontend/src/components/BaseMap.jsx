// 위성사진 / 일반 지도 전환이 되는 공통 지도
import { useState } from 'react'
import { MapContainer, TileLayer } from 'react-leaflet'

const LAYERS = {
  satellite: {
    label: '위성',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Tiles &copy; Esri',
    maxNativeZoom: 19,
  },
  street: {
    label: '일반',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; OpenStreetMap contributors',
    maxNativeZoom: 19,
  },
}

export default function BaseMap({ children, switcher = true, className = '', ...props }) {
  const [base, setBase] = useState('satellite')
  const layer = LAYERS[base]
  return (
    <div className={`map-wrap ${className}`}>
      <MapContainer className="map" zoomControl={false} attributionControl {...props}>
        <TileLayer key={base} url={layer.url} attribution={layer.attribution} maxNativeZoom={layer.maxNativeZoom} maxZoom={20} />
        {children}
      </MapContainer>
      {switcher && (
        <div className="map-switch" role="group" aria-label="배경 지도">
          {Object.entries(LAYERS).map(([k, v]) => (
            <button key={k} type="button" className={base === k ? 'on' : ''} aria-pressed={base === k} onClick={() => setBase(k)}>
              {v.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
