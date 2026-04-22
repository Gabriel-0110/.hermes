FROM node:20-alpine

WORKDIR /workspace

COPY package.json ./
COPY apps/web/package.json ./apps/web/package.json

RUN npm install

COPY . .

WORKDIR /workspace/apps/web

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0"]
