-- Create the database if it doesn't exist
CREATE DATABASE IF NOT EXISTS app_db;

-- Use the newly created database
USE app_db;

-- Table for users
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL
);

-- Table for platform information
CREATE TABLE IF NOT EXISTS platforms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,
    image_url VARCHAR(255),
    grafana_url VARCHAR(255),
    manage_type VARCHAR(50),
    manage_url VARCHAR(255)
);

-- Table for events and actions logs
CREATE TABLE IF NOT EXISTS events_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    action VARCHAR(255) NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Table for platform tracker documents
CREATE TABLE IF NOT EXISTS documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    platform_name VARCHAR(255) NOT NULL,
    doc_type VARCHAR(255),
    doc_name VARCHAR(255),
    version VARCHAR(50),
    path VARCHAR(255)
);

-- Insert initial admin and viewer users (PASSWORDS ARE NOT HASHED!)
INSERT INTO users (username, email, password, role) VALUES
('admin', 'admin@example.com', 'adminpass', 'Admin'),
('viewer', 'viewer@example.com', 'viewerpass', 'Viewer');

-- Insert initial platform data
INSERT INTO platforms (name, status, image_url, grafana_url, manage_type, manage_url) VALUES
('Ayla', 'Online', 'https://placehold.co/100x100/A0E7E5/000000?text=Ayla', 'https://grafana.example.com/d/ayla', 'ssh', 'ssh://user@ayla.example.com'),
('SAH', 'Offline', 'https://placehold.co/100x100/F9D0A7/000000?text=SAH', 'https://grafana.example.com/d/sah', 'ssh', 'ssh://user@sah.example.com'),
('CIOT', 'Online', 'https://placehold.co/100x100/C4D1FF/000000?text=CIOT', 'https://grafana.example.com/d/ciot', 'ssh', 'ssh://user@ciot.example.com'),
('AI', 'Online', 'https://placehold.co/100x100/FFD6A5/000000?text=AI', 'https://grafana.example.com/d/ai', 'ssh', 'ssh://user@ai.example.com'),
('SAQR', 'Online', 'https://placehold.co/100x100/FFABAB/000000?text=SAQR', 'https://grafana.example.com/d/saqr', 'rdp', 'rdp://user@saqr.example.com'),
('VSAAS', 'Offline', 'https://placehold.co/100x100/E3F6F5/000000?text=VSAAS', 'https://grafana.example.com/d/vsaas', 'ssh', 'ssh://user@vsaas.example.com'),
('FDH', 'Online', 'https://placehold.co/100x100/C4F1F9/000000?text=FDH', 'https://grafana.example.com/d/fdh', 'rdp', 'rdp://user@fdh.example.com'),
('Novatique', 'Online', 'https://placehold.co/100x100/A7C7E7/000000?text=Novatique', 'https://grafana.example.com/d/novatique', 'rdp', 'rdp://user@novatique.example.com');
