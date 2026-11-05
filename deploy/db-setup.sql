-- Run once on RDS (PostgreSQL) as the admin user. One database per service.
CREATE USER cinema_user WITH PASSWORD 'CHANGE_ME';
CREATE DATABASE user_db    OWNER cinema_user;
CREATE DATABASE product_db OWNER cinema_user;
CREATE DATABASE order_db   OWNER cinema_user;
-- Tables are created automatically when each service starts.

-- To make someone an admin (can add movies/shows):
--   \c user_db
--   UPDATE users SET role='admin' WHERE email='admin@example.com';
