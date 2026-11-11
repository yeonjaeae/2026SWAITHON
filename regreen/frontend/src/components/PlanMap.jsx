// 후보지와 설계 결과를 보여주는 고정 지도 (03 결과 비교, 04 리포트)
import { useEffect, useMemo } from 'react'
import { CircleMarker, GeoJSON, useMap } from 'react-leaflet'
import * as turf from '@turf/turf'
import BaseMap from './BaseMap.jsx'
import { randomPointsIn } from '../geo.js'

function Fit({ geometry }) {
  const map = useMap()
  useEffect(() => {
    const [w, s, e, n] = turf.bbox(geometry)
    map.fitBounds([[s, w], [n, e]], { padding: [30, 30], maxZoom: 19 })
  }, [geometry, map])
  return null
}

const STATIC = { dragging: false, zoomControl: false, scrollWheelZoom: false, doubleClickZoom: false, touchZoom: false, boxZoom: false, keyboard: false }

export default function PlanMap({ candidate, result, after = false, protect = [], className = '' }) {
  const geom = candidate.feature.geometry
  const green = result?.editable_geometry
  // 나무·관목 위치는 매번 바뀌지 않게 결과가 바뀔 때만 새로 뽑는다
  const trees = useMemo(() => (after && green ? randomPointsIn(green, Math.min(result.plant_count?.tree ?? 0, 150)) : []), [after, green, result?.plant_count?.tree])
  const shrubs = useMemo(() => (after && green ? randomPointsIn(green, Math.min(Math.round((result.plant_count?.shrub ?? 0) / 8), 300)) : []), [after, green, result?.plant_count?.shrub])
  return (
    <BaseMap className={className} switcher={false} center={[37.55, 126.97]} zoom={17} maxZoom={20} {...STATIC}>
      <Fit geometry={geom} />
      <GeoJSON data={geom} interactive={false} style={{ color: '#F5F3EC', weight: 3, dashArray: after ? '' : '8 6', fillOpacity: 0 }} />
      {after && green && <GeoJSON key={`g-${result.green_area_m2}`} data={green} interactive={false} style={{ color: '#2E7D57', weight: 2, fillColor: '#7CC47F', fillOpacity: 0.6 }} />}
      {after && protect.map((g, i) => <GeoJSON key={`p-${i}`} data={g} interactive={false} style={{ color: '#A06A10', weight: 2, fillColor: '#E4B34D', fillOpacity: 0.45 }} />)}
      {shrubs.map(([lng, lat], i) => <CircleMarker key={`s${i}`} center={[lat, lng]} radius={3.5} interactive={false} pathOptions={{ color: '#E8F5D8', weight: 1, fillColor: '#A3C93A', fillOpacity: 0.95 }} />)}
      {trees.map(([lng, lat], i) => <CircleMarker key={`t${i}`} center={[lat, lng]} radius={6} interactive={false} pathOptions={{ color: '#F5F3EC', weight: 1, fillColor: '#1F5A33', fillOpacity: 0.95 }} />)}
    </BaseMap>
  )
}
