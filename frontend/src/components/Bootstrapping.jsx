import { bootstrap } from "../api";

export default function Bootstrapping() {
  const handle = async () => {
    const res = await bootstrap();
    alert(`Before: ${res.data.before}, After: ${res.data.after}`);
  };

  return <button onClick={handle}>Refresh Ciphertext</button>;
}