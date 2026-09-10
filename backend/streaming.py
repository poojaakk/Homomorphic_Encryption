import asyncio
import random

async def stream_data(queue):
    while True:
        data = [random.uniform(20, 40)]
        await queue.put(data)
        print("Streaming:", data)   # 👈 ADD THIS LINE
        await asyncio.sleep(1)