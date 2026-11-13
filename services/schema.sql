-- ==============================================================================
-- Fresher Job Intelligence & Student Placement Pipeline
-- Database Schema: PostgreSQL 16
-- Design Specification: v1.0 (Nov 2026)
-- Target: India (Mumbai + Hyderabad) · Rolling 48-hour freshness
-- ==============================================================================

-- Enable UUID extension for cryptographic primary keys
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ------------------------------------------------------------------------------
-- 1. Pipeline Runs (Observe & Control)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(30) DEFAULT 'RUNNING' CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED', 'PARTIAL')),
    raw_collected_count INT DEFAULT 0,
    fresh_verified_count INT DEFAULT 0,
    hr_enriched_count INT DEFAULT 0,
    student_dispatched_count INT DEFAULT 0,
    cost_usd NUMERIC(8, 4) DEFAULT 0.0000,
    error_summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_runs_status ON runs(status);
CREATE INDEX idx_runs_started_at ON runs(started_at DESC);

-- ------------------------------------------------------------------------------
-- 2. Companies
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS companies (
    company_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(255) NOT NULL UNIQUE,
    clean_domain VARCHAR(255),
    careers_url TEXT,
    linkedin_url TEXT,
    headquarters_city VARCHAR(100),
    is_blacklisted BOOLEAN DEFAULT FALSE,
    blacklist_reason VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_companies_domain ON companies(clean_domain);
CREATE INDEX idx_companies_canonical ON companies(canonical_name);

-- ------------------------------------------------------------------------------
-- 3. Verified Fresher Jobs (Source of Truth)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_key CHAR(64) NOT NULL UNIQUE, -- SHA-256 (canonical_title + company + city + url)
    source_platform VARCHAR(50) NOT NULL CHECK (source_platform IN ('linkedin', 'naukri', 'indeed', 'foundit', 'other')),
    role_track VARCHAR(100) NOT NULL CHECK (role_track IN (
        'Data Analytics', 
        'Business Analytics', 
        'Analyst', 
        'MIS Executive', 
        'Web Development', 
        'Full Stack Development'
    )),
    title VARCHAR(300) NOT NULL,
    company_id UUID REFERENCES companies(company_id) ON DELETE SET NULL,
    company_name VARCHAR(255) NOT NULL,
    city VARCHAR(100) NOT NULL CHECK (city IN ('Mumbai', 'Hyderabad', 'Hybrid - Mumbai', 'Hybrid - Hyderabad', 'Remote')),
    location_raw VARCHAR(255),
    date_posted TIMESTAMP WITH TIME ZONE NOT NULL,
    experience_min NUMERIC(3,1) DEFAULT 0.0,
    experience_max NUMERIC(3,1) DEFAULT 1.0,
    salary_min NUMERIC(12,2),
    salary_max NUMERIC(12,2),
    salary_currency VARCHAR(10) DEFAULT 'INR',
    job_url TEXT NOT NULL,
    apply_url TEXT,
    description_text TEXT,
    trust_score INT NOT NULL DEFAULT 85 CHECK (trust_score BETWEEN 0 AND 100),
    review_status VARCHAR(30) DEFAULT 'AUTO_APPROVED' CHECK (review_status IN ('AUTO_APPROVED', 'MANUAL_REVIEW', 'REJECTED')),
    is_active BOOLEAN DEFAULT TRUE,
    first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP + INTERVAL '90 days')
);

CREATE INDEX idx_jobs_key ON jobs(job_key);
CREATE INDEX idx_jobs_track_city ON jobs(role_track, city);
CREATE INDEX idx_jobs_date_posted ON jobs(date_posted DESC);
CREATE INDEX idx_jobs_active_score ON jobs(is_active, trust_score DESC);

-- ------------------------------------------------------------------------------
-- 4. HR Contacts & Discovery Layer
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hr_contacts (
    contact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(company_id) ON DELETE CASCADE,
    job_id UUID REFERENCES jobs(job_id) ON DELETE CASCADE,
    full_name VARCHAR(150),
    job_title VARCHAR(150),
    email VARCHAR(255),
    phone VARCHAR(50),
    email_source VARCHAR(50) CHECK (email_source IN ('direct_jd', 'company_domain', 'hunter_io', 'apollo', 'manual')),
    hunter_status VARCHAR(50) DEFAULT 'UNVERIFIED' CHECK (hunter_status IN ('VALID', 'ACCEPT_ALL', 'INVALID', 'DISPOSABLE', 'UNVERIFIED')),
    mx_record_valid BOOLEAN DEFAULT FALSE,
    linkedin_search_url TEXT,
    google_call_search_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_hr_email ON hr_contacts(email);
CREATE INDEX idx_hr_company ON hr_contacts(company_id);

-- ------------------------------------------------------------------------------
-- 5. Students Roster & Preferences
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS students (
    student_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(30),
    telegram_chat_id VARCHAR(100),
    whatsapp_opt_in BOOLEAN DEFAULT FALSE,
    whatsapp_opt_in_at TIMESTAMP WITH TIME ZONE,
    target_track VARCHAR(100) NOT NULL,
    target_city VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_students_active ON students(is_active, target_track, target_city);

-- ------------------------------------------------------------------------------
-- 6. Student Matches (Deduplicated Recommendations)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS matches (
    match_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID REFERENCES students(student_id) ON DELETE CASCADE,
    job_id UUID REFERENCES jobs(job_id) ON DELETE CASCADE,
    match_score INT DEFAULT 90,
    status VARCHAR(30) DEFAULT 'MATCHED' CHECK (status IN ('MATCHED', 'DELIVERED', 'CLICKED', 'APPLIED', 'SKIPPED')),
    matched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id, job_id)
);

CREATE INDEX idx_matches_student ON matches(student_id, status);

-- ------------------------------------------------------------------------------
-- 7. Deliveries (Student Digest Outbound Audit)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID REFERENCES students(student_id) ON DELETE CASCADE,
    job_id UUID REFERENCES jobs(job_id) ON DELETE CASCADE,
    channel VARCHAR(30) NOT NULL CHECK (channel IN ('telegram', 'whatsapp', 'email_brevo')),
    dispatch_date DATE NOT NULL DEFAULT CURRENT_DATE,
    idempotency_key VARCHAR(255) NOT NULL UNIQUE, -- student_id + dispatch_date + channel
    status VARCHAR(30) DEFAULT 'SENT' CHECK (status IN ('PENDING', 'SENT', 'FAILED', 'BOUNCED')),
    provider_response_id VARCHAR(150),
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_deliveries_idempotency ON deliveries(idempotency_key);
CREATE INDEX idx_deliveries_date ON deliveries(dispatch_date);

-- ------------------------------------------------------------------------------
-- 8. HR Outreach Campaigns (Brevo 3-Step Sequence)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outreach (
    outreach_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id UUID REFERENCES hr_contacts(contact_id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(company_id) ON DELETE SET NULL,
    sequence_stage VARCHAR(30) NOT NULL CHECK (sequence_stage IN ('DAY_0_INTRO', 'DAY_4_VALUE_BUMP', 'DAY_10_BREAKUP')),
    channel VARCHAR(30) DEFAULT 'brevo_email' CHECK (channel IN ('brevo_email', 'telecalling_manual')),
    scheduled_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(30) DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'SENT', 'OPENED', 'REPLIED', 'FAILED', 'OPT_OUT')),
    telecaller_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_outreach_stage_status ON outreach(sequence_stage, status);

-- ------------------------------------------------------------------------------
-- 9. Errors & System Alerts
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS errors (
    error_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES runs(run_id) ON DELETE SET NULL,
    component_name VARCHAR(100) NOT NULL,
    severity VARCHAR(20) DEFAULT 'ERROR' CHECK (severity IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    error_message TEXT NOT NULL,
    payload_snapshot JSONB,
    alert_dispatched_telegram BOOLEAN DEFAULT FALSE,
    occurred_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_errors_severity ON errors(severity, occurred_at DESC);
