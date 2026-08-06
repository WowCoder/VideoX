FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

EXPOSE 5273

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
