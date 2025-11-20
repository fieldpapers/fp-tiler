FROM public.ecr.aws/lambda/nodejs:22 AS builder

WORKDIR /var/task

COPY package*.json ./
RUN npm ci

COPY tsconfig.json ./
COPY src ./src
RUN npx tsc

FROM public.ecr.aws/lambda/nodejs:22

WORKDIR /var/task

COPY package*.json ./
RUN npm ci --omit=dev

COPY --from=builder /var/task/dist/ ./

ENV NODE_ENV=production

CMD ["index.handler"]
