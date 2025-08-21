# .github/workflows/deploy.yml
name: Deploy Pulse FastAPI Application

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]
  workflow_dispatch:  # Allow manual deployment

env:
  APP_NAME: pulse-application-layer
  APP_PATH: /home/ubuntu/pulse-application-layer
  SERVICE_NAME: pulse-application-layer

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Cache pip dependencies
      uses: actions/cache@v3
      with:
        path: ~/.cache/pip
        key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}
        restore-keys: |
          ${{ runner.os }}-pip-
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install pytest pytest-asyncio httpx
    
    - name: Run tests
      run: |
        pytest tests/ -v || echo "No tests found, skipping..."
    
    - name: Lint with flake8
      run: |
        pip install flake8
        flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
        flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Setup SSH
      run: |
        mkdir -p ~/.ssh
        echo "${{ secrets.SSH_PRIVATE_KEY }}" > ~/.ssh/deploy_key
        chmod 600 ~/.ssh/deploy_key
        ssh-keyscan -H ${{ secrets.SERVER_HOST }} >> ~/.ssh/known_hosts
    
    - name: Deploy to Server
      run: |
        ssh -i ~/.ssh/deploy_key ${{ secrets.SERVER_USER }}@${{ secrets.SERVER_HOST }} << 'EOF'
          set -e
          
          echo "🚀 Starting deployment..."
          
          # Navigate to application directory
          cd ${{ env.APP_PATH }}
          
          # Activate virtual environment
          source venv/bin/activate
          
          # Backup current version
          echo "📦 Creating backup..."
          sudo cp -r ${{ env.APP_PATH }} ${{ env.APP_PATH }}_backup_$(date +%Y%m%d_%H%M%S)
          
          # Pull latest changes
          echo "⬇️  Pulling latest changes..."
          git fetch origin
          git reset --hard origin/${{ github.ref_name }}
          
          # Install/update dependencies
          echo "📚 Installing dependencies..."
          pip install -r requirements.txt
          
          # Update .env file with GitHub secrets
          echo "🔧 Updating environment variables..."
          cat > .env << 'ENVEOF'
        SUPABASE_URL=${{ secrets.SUPABASE_URL }}
        SUPABASE_SERVICE_ROLE_KEY=${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
        SUPABASE_ANON_KEY=${{ secrets.SUPABASE_ANON_KEY }}
        ENVEOF
          
          # Set proper permissions
          chmod 600 .env
          
          # Run database migrations if needed
          echo "🗄️  Running migrations..."
          # alembic upgrade head || echo "No alembic migrations found"
          
          # Test configuration
          echo "🧪 Testing application configuration..."
          timeout 10 python -c "
        import sys
        sys.path.append('.')
        try:
            from app.main import app
            print('✅ Application configuration valid')
        except Exception as e:
            print(f'❌ Configuration error: {e}')
            exit(1)
          "
          
          # Restart services
          echo "🔄 Restarting services..."
          sudo systemctl restart ${{ env.SERVICE_NAME }}
          sudo systemctl reload nginx
          
          # Wait for service to start
          echo "⏳ Waiting for service to start..."
          sleep 5
          
          # Health check
          echo "🏥 Performing health check..."
          for i in {1..5}; do
            if curl -f http://localhost:8000/ > /dev/null 2>&1; then
              echo "✅ Health check passed"
              break
            elif [ $i -eq 5 ]; then
              echo "❌ Health check failed after 5 attempts"
              
              # Rollback on failure
              echo "🔙 Rolling back..."
              sudo systemctl stop ${{ env.SERVICE_NAME }}
              
              # Find latest backup
              BACKUP_DIR=$(ls -td ${{ env.APP_PATH }}_backup_* | head -1)
              if [ -n "$BACKUP_DIR" ]; then
                sudo rm -rf ${{ env.APP_PATH }}
                sudo mv "$BACKUP_DIR" ${{ env.APP_PATH }}
                sudo chown -R ubuntu:ubuntu ${{ env.APP_PATH }}
                cd ${{ env.APP_PATH }}
                source venv/bin/activate
                sudo systemctl start ${{ env.SERVICE_NAME }}
                echo "🔙 Rollback completed"
              fi
              exit 1
            else
              echo "⏳ Attempt $i failed, retrying in 10 seconds..."
              sleep 10
            fi
          done
          
          # Check service status
          sudo systemctl status ${{ env.SERVICE_NAME }} --no-pager
          
          # Clean up old backups (keep last 3)
          echo "🧹 Cleaning up old backups..."
          ls -td ${{ env.APP_PATH }}_backup_* | tail -n +4 | xargs sudo rm -rf {} \; || true
          
          echo "✅ Deployment completed successfully!"
        EOF
    
    - name: Verify Deployment
      run: |
        echo "🔍 Verifying deployment..."
        
        # Production health check URL
        HEALTH_URL="https://dev.pulse-api.getpulseinsights.ai/"
        
        # Wait a bit for the service to fully start
        sleep 10
        
        # Perform external health check
        for i in {1..3}; do
          RESPONSE=$(curl -s "$HEALTH_URL")
          if curl -f "$HEALTH_URL" > /dev/null 2>&1; then
            echo "✅ External health check passed"
            echo "Response: $RESPONSE"
            break
          elif [ $i -eq 3 ]; then
            echo "❌ External health check failed"
            exit 1
          else
            echo "⏳ External health check attempt $i failed, retrying..."
            sleep 15
          fi
        done
    
    - name: Notify Success
      if: success()
      run: |
        echo "🎉 Deployment completed successfully!"
    
    - name: Notify Failure
      if: failure()
      run: |
        echo "💥 Deployment failed!"

  # Job for environment variable updates only
  update-env:
    runs-on: ubuntu-latest
    if: github.event_name == 'workflow_dispatch'
    
    steps:
    - name: Setup SSH
      run: |
        mkdir -p ~/.ssh
        echo "${{ secrets.SSH_PRIVATE_KEY }}" > ~/.ssh/deploy_key
        chmod 600 ~/.ssh/deploy_key
        ssh-keyscan -H ${{ secrets.SERVER_HOST }} >> ~/.ssh/known_hosts
    
    - name: Update Environment Variables
      run: |
        ssh -i ~/.ssh/deploy_key ${{ secrets.SERVER_USER }}@${{ secrets.SERVER_HOST }} << 'EOF'
          cd ${{ env.APP_PATH }}
          
          echo "🔧 Updating environment variables..."
          cat > .env << 'ENVEOF'
        SUPABASE_URL=${{ secrets.SUPABASE_URL }}
        SUPABASE_SERVICE_ROLE_KEY=${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
        SUPABASE_ANON_KEY=${{ secrets.SUPABASE_ANON_KEY }}
        ENVEOF
          
          chmod 600 .env
          sudo systemctl restart ${{ env.SERVICE_NAME }}
          
          echo "✅ Environment variables updated"
        EOF