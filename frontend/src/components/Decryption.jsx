import { decrypt } from "../api";

export default function Decryption() {
  const handle = async () => {
    const res = await decrypt();
    alert(`Result: ${res.data.result}`);
  };

  return <button onClick={handle}>Decrypt</button>;
}