import asyncio
from applo.db import init_db, get_session, JobListingORM
from applo.pipeline.optimizer import ResumeOptimizer
from applo.resume.generator import ResumeGenerator
from applo.resume.parser import load_or_parse_resume
from applo.config import settings
from applo.utils.logger import logger


async def main():
    init_db()

    resume_data = load_or_parse_resume(settings.master_resume_path)

    # grab first job with a description from DB
    with get_session() as session:
        job = session.query(JobListingORM).filter(
            JobListingORM.description != None,
            JobListingORM.description != ""
        ).first()

    if not job:
        print("No jobs with descriptions in DB. Run scraper first.")
        return

    # optimize
    optimizer = ResumeOptimizer()
    result = optimizer.optimize(job.title, job.company, job.description)

    print("\n--- OPTIMIZED SUMMARY ---")
    print(result.get("summary", ""))
    print("\n--- OPTIMIZED SKILLS ---")
    print(result.get("skills", ""))
    print("\n--- TOP 3 BULLETS ---")
    for b in result.get("experience_bullets", []):
        print(f"  • {b}")
    print("\n--- COVER LETTER (preview) ---")
    print(result.get("cover_letter", "")[:500])
    print("\n--- NOTES ---")
    print(result.get("optimization_notes", ""))

    # generate PDFs
    generator = ResumeGenerator()
    generator.generate(
        output_path="data/output/test_resume.pdf",
        resume_data=resume_data,
        optimized=result,
    )
    generator.generate_cover_letter(
        output_path="data/output/test_cover_letter.pdf",
        cover_letter_text=result.get("cover_letter", ""),
        candidate_name="Kevin Kimani",
    )
    print("\nPDFs generated — check data/output/")


asyncio.run(main())