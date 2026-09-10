import { useEffect, useState } from "react";
import { getNoise } from "../api";

export default function NoiseMonitor() {
  const [noise, setNoise] = useState(0);

  useEffect(() => {
    setInterval(async () => {
      const res = await getNoise();
      setNoise(res.data.noise);
    }, 1000);
  }, []);

  return <div>Noise Level: {noise}</div>;
}