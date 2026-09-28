import asyncio
from app.cli.seed_demo import seed_demo

if __name__ == "__main__":
    print("Resetting database to pristine hero demo state...")
    asyncio.run(seed_demo())
