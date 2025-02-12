FROM node:22

WORKDIR /app
ADD . /app/
RUN chown -R node:node /app

USER node

RUN npm install

VOLUME ["/app"]
EXPOSE 8080

CMD npm start
