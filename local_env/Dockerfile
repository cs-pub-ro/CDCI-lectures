FROM node:20

# Install NGINX
RUN apt-get update && apt-get install -y nginx && rm -rf /var/lib/apt/lists/*

# Install the latest Slidev dependencies locally inside the image's /app directory
WORKDIR /app
RUN npm init -y && npm install \
    @slidev/cli@latest \
    @slidev/theme-default@latest \
    unocss@latest \
    playwright@latest \
    @fontsource/libertinus-serif@latest

# Slidev hardcodes playwright-chromium, but we can symlink it to playwright since the registry sometimes blocks playwright-chromium
RUN cd /app/node_modules && ln -s playwright playwright-chromium

# Install Playwright dependencies
RUN npx playwright install-deps
RUN npx playwright install chromium

# Copy startup script
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 80

CMD ["/start.sh"]
