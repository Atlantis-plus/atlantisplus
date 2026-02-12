"""
Enrichment Service

External data enrichment using People Data Labs API.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional
from uuid import UUID

import httpx

from ..config import get_settings
from ..supabase_client import get_supabase_admin
from ..utils import normalize_linkedin_url
from .embedding import generate_embedding


@dataclass
class EnrichmentQuota:
    """Current enrichment quota status."""
    daily_used: int
    daily_limit: int
    monthly_used: int
    monthly_limit: int
    can_enrich: bool
    reason: Optional[str] = None


@dataclass
class EnrichmentResult:
    """Result of enrichment attempt."""
    success: bool
    person_id: UUID
    assertions_created: int
    identities_created: int
    error: Optional[str] = None


class EnrichmentService:
    """Service for enriching person profiles with external data."""

    PDL_BASE_URL = "https://api.peopledatalabs.com/v5"

    def __init__(self):
        self.settings = get_settings()
        self.supabase = get_supabase_admin()

    async def get_quota(self, owner_id: UUID) -> EnrichmentQuota:
        """Get current enrichment quota for user."""
        today = date.today()
        month_start = today.replace(day=1)

        # Get or create quota record
        result = self.supabase.from_("enrichment_quota").select("*").eq(
            "owner_id", str(owner_id)
        ).execute()

        if not result.data:
            # Create new quota record
            self.supabase.from_("enrichment_quota").insert({
                "owner_id": str(owner_id),
                "monthly_used": 0,
                "monthly_limit": self.settings.pdl_monthly_limit,
                "daily_used": 0,
                "daily_limit": self.settings.pdl_daily_limit,
                "last_daily_reset": str(today),
                "last_monthly_reset": str(month_start)
            }).execute()

            return EnrichmentQuota(
                daily_used=0,
                daily_limit=self.settings.pdl_daily_limit,
                monthly_used=0,
                monthly_limit=self.settings.pdl_monthly_limit,
                can_enrich=bool(self.settings.pdl_api_key)
            )

        quota = result.data[0]

        # Reset counters if needed
        last_daily = datetime.strptime(quota["last_daily_reset"], "%Y-%m-%d").date()
        last_monthly = datetime.strptime(quota["last_monthly_reset"], "%Y-%m-%d").date()

        updates = {}
        if today > last_daily:
            updates["daily_used"] = 0
            updates["last_daily_reset"] = str(today)

        if today.replace(day=1) > last_monthly:
            updates["monthly_used"] = 0
            updates["last_monthly_reset"] = str(month_start)

        if updates:
            updates["updated_at"] = datetime.utcnow().isoformat()
            self.supabase.from_("enrichment_quota").update(updates).eq(
                "owner_id", str(owner_id)
            ).execute()

            if "daily_used" in updates:
                quota["daily_used"] = 0
            if "monthly_used" in updates:
                quota["monthly_used"] = 0

        can_enrich = True
        reason = None

        if not self.settings.pdl_api_key:
            can_enrich = False
            reason = "PDL API key not configured"
        elif quota["daily_used"] >= quota["daily_limit"]:
            can_enrich = False
            reason = f"Daily limit reached ({quota['daily_limit']})"
        elif quota["monthly_used"] >= quota["monthly_limit"]:
            can_enrich = False
            reason = f"Monthly limit reached ({quota['monthly_limit']})"

        return EnrichmentQuota(
            daily_used=quota["daily_used"],
            daily_limit=quota["daily_limit"],
            monthly_used=quota["monthly_used"],
            monthly_limit=quota["monthly_limit"],
            can_enrich=can_enrich,
            reason=reason
        )

    async def _increment_quota(self, owner_id: UUID):
        """Increment quota counters after successful enrichment."""
        result = self.supabase.from_("enrichment_quota").select(
            "daily_used, monthly_used"
        ).eq("owner_id", str(owner_id)).execute()

        if result.data:
            self.supabase.from_("enrichment_quota").update({
                "daily_used": result.data[0]["daily_used"] + 1,
                "monthly_used": result.data[0]["monthly_used"] + 1,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("owner_id", str(owner_id)).execute()

    async def _call_pdl_api(self, params: dict) -> Optional[dict]:
        """Call People Data Labs person enrichment API."""
        if not self.settings.pdl_api_key:
            return None

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.PDL_BASE_URL}/person/enrich",
                headers={"X-Api-Key": self.settings.pdl_api_key},
                params=params,
                timeout=30.0
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None  # Person not found
            else:
                raise Exception(f"PDL API error: {response.status_code} - {response.text}")

    async def enrich_person(
        self,
        owner_id: UUID,
        person_id: UUID
    ) -> EnrichmentResult:
        """
        Enrich a person's profile with external data.

        Looks up the person using available identifiers (email, LinkedIn, name)
        and creates new assertions/identities from the results.
        """
        # Check quota
        quota = await self.get_quota(owner_id)
        if not quota.can_enrich:
            return EnrichmentResult(
                success=False,
                person_id=person_id,
                assertions_created=0,
                identities_created=0,
                error=quota.reason
            )

        # Get person and their identities
        person = self.supabase.from_("person").select(
            "person_id, display_name, enrichment_status"
        ).eq("person_id", str(person_id)).eq("owner_id", str(owner_id)).execute()

        if not person.data:
            return EnrichmentResult(
                success=False,
                person_id=person_id,
                assertions_created=0,
                identities_created=0,
                error="Person not found"
            )

        person_data = person.data[0]

        # Get identities
        identities = self.supabase.from_("identity").select(
            "namespace, value"
        ).eq("person_id", str(person_id)).execute()

        # Build PDL query params
        params = {}
        for identity in identities.data or []:
            ns = identity["namespace"]
            val = identity["value"]

            if ns == "linkedin_url":
                # Only use real profile URLs (contain /in/), skip search URLs
                if "/in/" in val:
                    params["profile"] = val
                else:
                    print(f"[ENRICHMENT] Skipping non-profile LinkedIn URL: {val}")
            elif ns == "email":
                params["email"] = val
            elif ns == "email_hash":
                # PDL doesn't support hashed emails, skip
                continue

        print(f"[ENRICHMENT] Params for PDL: {params}")

        # If no identities, try name-based lookup
        if not params:
            name_parts = person_data["display_name"].split()
            if len(name_parts) >= 2:
                params["first_name"] = name_parts[0]
                params["last_name"] = " ".join(name_parts[1:])
            else:
                return EnrichmentResult(
                    success=False,
                    person_id=person_id,
                    assertions_created=0,
                    identities_created=0,
                    error="No identifiers available for lookup"
                )

        # Update status to processing
        self.supabase.from_("person").update({
            "enrichment_status": "processing",
            "updated_at": datetime.utcnow().isoformat()
        }).eq("person_id", str(person_id)).execute()

        # Create enrichment job
        job = self.supabase.from_("enrichment_job").insert({
            "owner_id": str(owner_id),
            "person_id": str(person_id),
            "status": "processing",
            "request_payload": params,
            "started_at": datetime.utcnow().isoformat()
        }).execute()

        job_id = job.data[0]["job_id"] if job.data else None

        try:
            # Call PDL API
            pdl_data = await self._call_pdl_api(params)

            if not pdl_data:
                self._update_job_status(job_id, "error", error="Person not found in PDL")
                self._update_person_status(person_id, "skipped")
                return EnrichmentResult(
                    success=False,
                    person_id=person_id,
                    assertions_created=0,
                    identities_created=0,
                    error="Person not found in external database"
                )

            # Process PDL response - extract nested "data" object
            pdl_person_data = pdl_data.get("data", pdl_data)
            print(f"[ENRICHMENT] PDL returned data keys: {list(pdl_person_data.keys())[:10]}")

            assertions_created, identities_created = await self._process_pdl_response(
                person_id, pdl_person_data
            )

            # Increment quota
            await self._increment_quota(owner_id)

            # Create _enriched_at service assertion
            self._create_enrichment_assertion(
                person_id=person_id,
                source="pdl",
                assertions_created=assertions_created,
                identities_created=identities_created
            )

            # Update job and person status
            self._update_job_status(job_id, "done", response=pdl_data)
            self._update_person_status(person_id, "done")

            return EnrichmentResult(
                success=True,
                person_id=person_id,
                assertions_created=assertions_created,
                identities_created=identities_created
            )

        except Exception as e:
            self._update_job_status(job_id, "error", error=str(e))
            self._update_person_status(person_id, "error")
            return EnrichmentResult(
                success=False,
                person_id=person_id,
                assertions_created=0,
                identities_created=0,
                error=str(e)
            )

    def _update_job_status(
        self,
        job_id: Optional[str],
        status: str,
        response: Optional[dict] = None,
        error: Optional[str] = None
    ):
        if not job_id:
            return

        update = {
            "status": status,
            "completed_at": datetime.utcnow().isoformat()
        }
        if response:
            update["response_payload"] = response
        if error:
            update["error_message"] = error

        self.supabase.from_("enrichment_job").update(update).eq("job_id", job_id).execute()

    def _update_person_status(self, person_id: UUID, status: str):
        self.supabase.from_("person").update({
            "enrichment_status": status,
            "last_enriched_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }).eq("person_id", str(person_id)).execute()

    def _create_enrichment_assertion(
        self,
        person_id: UUID,
        source: str,
        assertions_created: int,
        identities_created: int
    ):
        """
        Create a service assertion to track enrichment status.

        Service predicates start with "_" and are used for internal tracking.
        """
        enriched_at = datetime.utcnow().isoformat()

        self.supabase.from_("assertion").insert({
            "subject_person_id": str(person_id),
            "predicate": "_enriched_at",
            "object_value": enriched_at,
            "object_json": {
                "source": source,
                "facts_added": assertions_created,
                "identities_added": identities_created,
                "timestamp": enriched_at
            },
            "scope": "system",
            "confidence": 1.0,
            "embedding": None  # Service assertions don't need embeddings
        }).execute()

    def _safe_list(self, value) -> list:
        """
        Safely convert PDL field to list.

        PDL API returns:
        - list: actual data
        - bool True: data exists but is hidden/requires credits
        - bool False: no data available
        - None: field not present

        Returns empty list for non-list values.
        """
        if isinstance(value, list):
            return value
        return []

    def _safe_str(self, value) -> Optional[str]:
        """
        Safely get string value from PDL field.

        PDL API returns:
        - str: actual data
        - bool True: data exists but is hidden
        - bool False: no data available
        - None: field not present

        Returns None for non-string values.
        """
        if isinstance(value, str):
            return value
        return None

    async def _process_pdl_response(
        self,
        person_id: UUID,
        data: dict
    ) -> tuple[int, int]:
        """
        Process PDL response and create assertions/identities.

        PDL API quirks handled:
        - Fields can be bool (true = exists but hidden, false = no data)
        - Arrays can be empty [], bool, or actual data
        - Nested objects may have bool fields too

        Returns (assertions_created, identities_created)
        """
        assertions_created = 0
        identities_created = 0

        # Job title → role_is
        job_title = self._safe_str(data.get("job_title"))
        if job_title:
            self._create_assertion(person_id, "role_is", job_title)
            assertions_created += 1

        # Company → works_at
        company = self._safe_str(data.get("job_company_name"))
        if company:
            self._create_assertion(person_id, "works_at", company)
            assertions_created += 1

        # Location → located_in
        location_parts = []
        locality = self._safe_str(data.get("location_locality"))
        country = self._safe_str(data.get("location_country"))
        if locality:
            location_parts.append(locality)
        if country:
            location_parts.append(country)
        if location_parts:
            self._create_assertion(person_id, "located_in", ", ".join(location_parts))
            assertions_created += 1

        # Skills → strong_at (PDL can return bool instead of array)
        skills = self._safe_list(data.get("skills"))
        for skill in skills[:5]:  # Limit to 5 skills
            # Each skill should be a string, but defensive check
            if isinstance(skill, str) and skill:
                self._create_assertion(person_id, "strong_at", skill)
                assertions_created += 1

        # LinkedIn → identity (normalized to consistent format)
        linkedin_url = self._safe_str(data.get("linkedin_url"))
        if linkedin_url:
            normalized_linkedin = normalize_linkedin_url(linkedin_url)
            if normalized_linkedin:
                if self._create_identity(person_id, "linkedin_url", normalized_linkedin):
                    identities_created += 1

        # Email → identity (hashed)
        # PDL "emails" can be: list of dicts, bool, or None
        emails = self._safe_list(data.get("emails"))
        for email in emails[:3]:
            # Each email should be dict with "address" key
            if isinstance(email, dict):
                address = email.get("address")
                if isinstance(address, str) and address:
                    email_hash = hashlib.sha256(address.lower().encode()).hexdigest()
                    if self._create_identity(person_id, "email_hash", email_hash):
                        identities_created += 1

        # Industry → assertion
        industry = self._safe_str(data.get("industry"))
        if industry:
            self._create_assertion(person_id, "background", f"Industry: {industry}")
            assertions_created += 1

        # Education → assertion
        # PDL "education" can be: list of dicts, bool, or None
        education = self._safe_list(data.get("education"))
        for edu in education[:2]:
            # Each edu should be dict with "school" object
            if not isinstance(edu, dict):
                continue

            school = edu.get("school")
            if not isinstance(school, dict):
                continue

            school_name = self._safe_str(school.get("name"))
            if not school_name:
                continue

            edu_text = school_name

            # Degrees is also a list that could have non-string elements
            degrees = self._safe_list(edu.get("degrees"))
            # Filter to only strings and non-empty
            valid_degrees = [d for d in degrees if isinstance(d, str) and d]
            if valid_degrees:
                edu_text = f"{', '.join(valid_degrees)} from {edu_text}"

            self._create_assertion(person_id, "background", f"Education: {edu_text}")
            assertions_created += 1

        # Experience → additional assertions for past companies
        experience = self._safe_list(data.get("experience"))
        # Skip first (primary/current) as we already have job_company_name
        for exp in experience[1:3]:  # Get 2 previous jobs
            if not isinstance(exp, dict):
                continue

            company_data = exp.get("company")
            if not isinstance(company_data, dict):
                continue

            company_name = self._safe_str(company_data.get("name"))
            if not company_name:
                continue

            title_data = exp.get("title")
            title_name = None
            if isinstance(title_data, dict):
                title_name = self._safe_str(title_data.get("name"))

            if title_name:
                exp_text = f"{title_name} at {company_name}"
            else:
                exp_text = f"Previously at {company_name}"

            self._create_assertion(person_id, "background", exp_text)
            assertions_created += 1

        # Social profiles → identities
        profiles = self._safe_list(data.get("profiles"))
        for profile in profiles:
            if not isinstance(profile, dict):
                continue

            network = self._safe_str(profile.get("network"))
            url = self._safe_str(profile.get("url"))

            if not network or not url:
                continue

            # Map network to our namespace
            namespace_map = {
                "linkedin": "linkedin_url",
                "twitter": "twitter_url",
                "facebook": "facebook_url",
                "github": "github_url",
            }

            namespace = namespace_map.get(network)
            if namespace and namespace != "linkedin_url":  # linkedin already handled above
                # Ensure URL has protocol
                if not url.startswith("http"):
                    url = f"https://{url}"
                if self._create_identity(person_id, namespace, url):
                    identities_created += 1

        return assertions_created, identities_created

    def _create_assertion(self, person_id: UUID, predicate: str, value: str):
        """Create an assertion with external scope."""
        embedding = generate_embedding(f"{predicate}: {value}")

        self.supabase.from_("assertion").insert({
            "subject_person_id": str(person_id),
            "predicate": predicate,
            "object_value": value,
            "scope": "external",
            "confidence": 0.7,  # Lower confidence for external data
            "embedding": embedding
        }).execute()

    def _create_identity(self, person_id: UUID, namespace: str, value: str) -> bool:
        """Create an identity if it doesn't already exist. Returns True if created."""
        # Check if exists
        existing = self.supabase.from_("identity").select("identity_id").eq(
            "namespace", namespace
        ).eq("value", value).execute()

        if existing.data:
            return False

        try:
            self.supabase.from_("identity").insert({
                "person_id": str(person_id),
                "namespace": namespace,
                "value": value,
                "verified": False
            }).execute()
            return True
        except Exception:
            return False  # Likely unique constraint violation

    async def get_enrichment_status(
        self,
        owner_id: UUID,
        person_id: UUID
    ) -> dict:
        """
        Get enrichment status for a person.

        Checks for _enriched_at service assertion to determine if enrichment
        has been performed.
        """
        # Verify person exists and belongs to owner
        person = self.supabase.from_("person").select(
            "person_id"
        ).eq("person_id", str(person_id)).eq("owner_id", str(owner_id)).execute()

        if not person.data:
            return {"status": "not_found"}

        # Check for _enriched_at service assertion
        enrichment_assertion = self.supabase.from_("assertion").select(
            "assertion_id, object_value, object_json, created_at"
        ).eq("subject_person_id", str(person_id)).eq(
            "predicate", "_enriched_at"
        ).order("created_at", desc=True).limit(1).execute()

        if enrichment_assertion.data:
            assertion = enrichment_assertion.data[0]
            return {
                "status": "enriched",
                "last_enriched_at": assertion.get("object_value"),
                "enrichment_details": assertion.get("object_json"),
                "last_job": None  # For backwards compatibility
            }

        # Get latest job if any (for processing/error states)
        job = self.supabase.from_("enrichment_job").select(
            "status, error_message, created_at, completed_at"
        ).eq("person_id", str(person_id)).order(
            "created_at", desc=True
        ).limit(1).execute()

        result = {
            "status": "not_enriched",
            "last_enriched_at": None
        }

        if job.data:
            job_status = job.data[0]["status"]
            # If job is processing, reflect that status
            if job_status == "processing":
                result["status"] = "processing"
            elif job_status == "error":
                result["status"] = "error"

            result["last_job"] = {
                "status": job_status,
                "error": job.data[0].get("error_message"),
                "completed_at": job.data[0].get("completed_at")
            }

        return result


# Singleton instance
_enrichment_service: Optional[EnrichmentService] = None


def get_enrichment_service() -> EnrichmentService:
    global _enrichment_service
    if _enrichment_service is None:
        _enrichment_service = EnrichmentService()
    return _enrichment_service
