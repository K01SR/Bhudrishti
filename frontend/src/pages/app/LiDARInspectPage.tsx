import LiDARInspector from '../../components/lidarinspector/LiDARInspector';
import { DEMO_ULPIN } from '../../constants';

export default function LiDARInspectPage() {
  return (
    <div style={{ position: 'absolute', inset: 0, minHeight: '100%', display: 'flex', overflow: 'hidden' }}>
      <LiDARInspector initialULPIN={DEMO_ULPIN} autoFocusSelection className="lidar-page" />
    </div>
  );
}