import { encrypt } from "../api";

export default function EncryptionPanel() {
  const handle = async () => {
    const res = await encrypt();
    alert(JSON.stringify(res.data));
  };

  return <button onClick={handle}>Encrypt</button>;
}