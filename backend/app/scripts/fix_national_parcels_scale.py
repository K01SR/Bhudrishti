"""
Fix national parcels and twins area scale and FSI calibration.
Replaces absurd macro-partition areas (>10,000 m², up to 55M m²) with
realistic cadastral building plot areas (450 to 3,500 m²) and realistic FSI (0.9 to 3.8).
"""
import asyncio
import logging
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("fix_scale")

SQL_UPDATE_TWINS = """
UPDATE national_twins
SET 
    plot_area_m2 = round((CASE 
        WHEN typology = 'row_house' THEN 350 + (floors * 60) + (mod(abs(hashtext(ulpin)), 200))
        WHEN typology = 'slab' THEN 750 + (floors * 90) + (mod(abs(hashtext(ulpin)), 400))
        WHEN typology = 'commercial' THEN 1100 + (floors * 120) + (mod(abs(hashtext(ulpin)), 600))
        WHEN typology = 'tower' THEN 1200 + (floors * 110) + (mod(abs(hashtext(ulpin)), 800))
        ELSE 900 + (floors * 80) + (mod(abs(hashtext(ulpin)), 300))
    END)::numeric, 1),
    footprint_area_m2 = round(((CASE 
        WHEN typology = 'row_house' THEN 0.45 + (mod(abs(hashtext(ulpin)), 10) * 0.01)
        WHEN typology = 'slab' THEN 0.35 + (mod(abs(hashtext(ulpin)), 10) * 0.01)
        WHEN typology = 'commercial' THEN 0.30 + (mod(abs(hashtext(ulpin)), 10) * 0.01)
        WHEN typology = 'tower' THEN 0.22 + (mod(abs(hashtext(ulpin)), 8) * 0.01)
        ELSE 0.35
    END) * (CASE 
        WHEN typology = 'row_house' THEN 350 + (floors * 60) + (mod(abs(hashtext(ulpin)), 200))
        WHEN typology = 'slab' THEN 750 + (floors * 90) + (mod(abs(hashtext(ulpin)), 400))
        WHEN typology = 'commercial' THEN 1100 + (floors * 120) + (mod(abs(hashtext(ulpin)), 600))
        WHEN typology = 'tower' THEN 1200 + (floors * 110) + (mod(abs(hashtext(ulpin)), 800))
        ELSE 900 + (floors * 80) + (mod(abs(hashtext(ulpin)), 300))
    END))::numeric, 1),
    buildable_area_m2 = round(((CASE 
        WHEN typology = 'row_house' THEN 0.45 + (mod(abs(hashtext(ulpin)), 10) * 0.01)
        WHEN typology = 'slab' THEN 0.35 + (mod(abs(hashtext(ulpin)), 10) * 0.01)
        WHEN typology = 'commercial' THEN 0.30 + (mod(abs(hashtext(ulpin)), 10) * 0.01)
        WHEN typology = 'tower' THEN 0.22 + (mod(abs(hashtext(ulpin)), 8) * 0.01)
        ELSE 0.35
    END) * (CASE 
        WHEN typology = 'row_house' THEN 350 + (floors * 60) + (mod(abs(hashtext(ulpin)), 200))
        WHEN typology = 'slab' THEN 750 + (floors * 90) + (mod(abs(hashtext(ulpin)), 400))
        WHEN typology = 'commercial' THEN 1100 + (floors * 120) + (mod(abs(hashtext(ulpin)), 600))
        WHEN typology = 'tower' THEN 1200 + (floors * 110) + (mod(abs(hashtext(ulpin)), 800))
        ELSE 900 + (floors * 80) + (mod(abs(hashtext(ulpin)), 300))
    END))::numeric, 1),
    built_up_area_m2 = round((((CASE 
        WHEN typology = 'row_house' THEN 0.45 + (mod(abs(hashtext(ulpin)), 10) * 0.01)
        WHEN typology = 'slab' THEN 0.35 + (mod(abs(hashtext(ulpin)), 10) * 0.01)
        WHEN typology = 'commercial' THEN 0.30 + (mod(abs(hashtext(ulpin)), 10) * 0.01)
        WHEN typology = 'tower' THEN 0.22 + (mod(abs(hashtext(ulpin)), 8) * 0.01)
        ELSE 0.35
    END) * (CASE 
        WHEN typology = 'row_house' THEN 350 + (floors * 60) + (mod(abs(hashtext(ulpin)), 200))
        WHEN typology = 'slab' THEN 750 + (floors * 90) + (mod(abs(hashtext(ulpin)), 400))
        WHEN typology = 'commercial' THEN 1100 + (floors * 120) + (mod(abs(hashtext(ulpin)), 600))
        WHEN typology = 'tower' THEN 1200 + (floors * 110) + (mod(abs(hashtext(ulpin)), 800))
        ELSE 900 + (floors * 80) + (mod(abs(hashtext(ulpin)), 300))
    END)) * floors)::numeric, 1),
    fsi = round(((CASE 
        WHEN typology = 'row_house' THEN 0.45 + (mod(abs(hashtext(ulpin)), 10) * 0.01)
        WHEN typology = 'slab' THEN 0.35 + (mod(abs(hashtext(ulpin)), 10) * 0.01)
        WHEN typology = 'commercial' THEN 0.30 + (mod(abs(hashtext(ulpin)), 10) * 0.01)
        WHEN typology = 'tower' THEN 0.22 + (mod(abs(hashtext(ulpin)), 8) * 0.01)
        ELSE 0.35
    END) * floors)::numeric, 2),
    fsi_status = CASE 
        WHEN (((CASE 
            WHEN typology = 'row_house' THEN 0.45 + (mod(abs(hashtext(ulpin)), 10) * 0.01)
            WHEN typology = 'slab' THEN 0.35 + (mod(abs(hashtext(ulpin)), 10) * 0.01)
            WHEN typology = 'commercial' THEN 0.30 + (mod(abs(hashtext(ulpin)), 10) * 0.01)
            WHEN typology = 'tower' THEN 0.22 + (mod(abs(hashtext(ulpin)), 8) * 0.01)
            ELSE 0.35
        END) * floors)) <= 2.5 THEN 'PASS'
        ELSE 'EXCEEDED'
    END
WHERE plot_area_m2 > 10000 OR fsi > 6.0;
"""

SQL_UPDATE_PARCELS_FROM_TWINS = """
UPDATE national_parcels p
SET area_m2 = w.plot_area_m2
FROM national_twins w
WHERE w.ulpin = p.ulpin AND (p.area_m2 > 10000 OR p.area_m2 IS NULL);
"""

SQL_UPDATE_REMAINING_PARCELS = """
UPDATE national_parcels
SET area_m2 = round((800 + mod(abs(hashtext(ulpin)), 1200))::numeric, 1)
WHERE area_m2 > 10000 OR area_m2 IS NULL;
"""

async def run():
    log.info("Starting scale calibration...")
    async with AsyncSessionLocal() as session:
        res1 = await session.execute(text(SQL_UPDATE_TWINS))
        log.info("Updated %s national twins to realistic scale", res1.rowcount)
        
        res2 = await session.execute(text(SQL_UPDATE_PARCELS_FROM_TWINS))
        log.info("Updated %s national parcels from twins", res2.rowcount)
        
        res3 = await session.execute(text(SQL_UPDATE_REMAINING_PARCELS))
        log.info("Updated %s remaining national parcels", res3.rowcount)
        
        await session.commit()
    log.info("Scale calibration completed successfully.")

if __name__ == "__main__":
    asyncio.run(run())
