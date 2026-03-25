import asyncio
from src.infrastructure.signal_repository import SignalRepository

async def main():
    repo = SignalRepository()
    await repo.initialize()
    stats = await repo.get_stats()
    print("Stats from script:", stats)
    await repo.close()

if __name__ == "__main__":
    asyncio.run(main())
