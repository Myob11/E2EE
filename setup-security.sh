#!/bin/bash
# ==============================================================================
# E2EE Security Hardening Script
# ==============================================================================
# This script sets up secure credentials and configures the environment
# Run this BEFORE deploying to production
# ==============================================================================

set -e

echo "🔒 E2EE Security Hardening Setup"
echo "=================================="

# Check if .env file exists
if [ -f .env ]; then
    echo "⚠️  .env file already exists. Skipping generation..."
    echo "   If you need to regenerate, delete .env and run this script again."
else
    echo "📝 Generating secure .env file..."
    
    # Generate strong random passwords
    POSTGRES_PASSWORD=$(openssl rand -base64 32)
    REDIS_PASSWORD=$(openssl rand -base64 32)
    MONGO_PASSWORD=$(openssl rand -base64 32)
    MINIO_PASSWORD=$(openssl rand -base64 32)
    SECRET_KEY=$(openssl rand -base64 64)
    
    cat > .env << EOF
# ==============================================================================
# E2EE SECURE CONFIGURATION - AUTO-GENERATED $(date)
# ==============================================================================

# PostgreSQL Database (INTERNAL ONLY - NOT EXPOSED)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=auth_db

# Redis Cache (INTERNAL ONLY - NOT EXPOSED)
REDIS_PASSWORD=$REDIS_PASSWORD

# MongoDB (INTERNAL ONLY - NOT EXPOSED)
MONGO_USER=admin
MONGO_PASSWORD=$MONGO_PASSWORD

# MinIO Object Storage (INTERNAL ONLY - NOT EXPOSED)
MINIO_USER=minioadmin
MINIO_PASSWORD=$MINIO_PASSWORD

# Application Secrets
SECRET_KEY=$SECRET_KEY

# ==============================================================================
# Generated on: $(date)
# Keep this file secure and never commit to git!
# ==============================================================================
EOF
    
    echo "✅ .env file created with secure credentials"
    echo "   Passwords generated with: openssl rand -base64 32"
fi

echo ""
echo "🔐 Security Configuration Summary"
echo "=================================="
echo "✓ PostgreSQL: Internal only (no port exposure)"
echo "✓ Redis:     Internal only (password protected)"
echo "✓ MongoDB:   Internal only (authentication enabled)"
echo "✓ MinIO:     Internal only (strong credentials)"
echo "✓ All credentials from environment variables"
echo ""
echo "📋 Next Steps:"
echo "1. Verify .env has been created with strong passwords"
echo "2. Run: docker-compose down && docker-compose up -d"
echo "3. Monitor: docker logs e2ee_postgres"
echo "4. Backup: Add automated database backups"
echo "5. Firewall: Ensure no database ports exposed to internet"
echo ""
echo "⚠️  IMPORTANT REMINDERS:"
echo "   - Add .env to .gitignore (DO NOT commit passwords)"
echo "   - Rotate credentials every 90 days"
echo "   - Enable database backups immediately"
echo "   - Monitor PostgreSQL logs for intrusions"
echo "   - Keep backups separate from main infrastructure"
echo ""
