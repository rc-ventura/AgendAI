FROM nginx:1.27-alpine

# Remove config padrão; o template é processado pelo entrypoint oficial da imagem
RUN rm /etc/nginx/conf.d/default.conf

COPY nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 8080
