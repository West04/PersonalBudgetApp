# Stage 1: Build Environment
# Use a Node.js image to build the app. Alpine is used for a smaller image size.
FROM node:20-alpine AS build

# Set the working directory inside the container
WORKDIR /app

# Copy package.json and package-lock.json to leverage Docker's layer caching.
# This step only re-runs if these files change.
COPY package.json package-lock.json ./

# Install all dependencies, including devDependencies needed for the build
RUN npm install

# Copy the rest of the application's source code
COPY ../.. .

# Run the build script defined in package.json
RUN npm run build


# Stage 2: Production Environment
# Use a slim, secure base image for the final container
FROM node:20-alpine AS production

WORKDIR /app

# Copy only the necessary files for production from the build stage
COPY --from=build /app/.output ./.output
COPY --from=build /app/package.json ./package.json
COPY --from=build /app/package-lock.json ./package-lock.json

# Install ONLY production dependencies
RUN npm install --omit=dev

# Expose the port the app will run on. Default for Nuxt is 3000.
EXPOSE 3000

# Set environment variables for the Nuxt server
# HOST=0.0.0.0 is crucial for the app to be accessible from outside the container
ENV HOST=0.0.0.0
ENV PORT=3000

# The command to start the Nuxt server in production mode
CMD ["node", ".output/server/index.mjs"]
