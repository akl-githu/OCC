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
    manage_url VARCHAR(255),
    progress_stage VARCHAR(50) NOT NULL DEFAULT 'CRC'
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
    path VARCHAR(255),
    comments TEXT
);

-- New table to store the progress history for each platform
CREATE TABLE platform_progress (
    id INT AUTO_INCREMENT PRIMARY KEY,
    platform_name VARCHAR(255) NOT NULL,
    progress_stage ENUM('CRC', 'RFP', 'RFQ', 'POC', 'ATP', 'RFS') NOT NULL,
    stage_date DATE NOT NULL,
    comments TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    --FOREIGN KEY (platform_name) REFERENCES platforms(name) ON DELETE CASCADE
);

-- Insert initial user data
INSERT INTO users (username, email, password, role) VALUES
('admin', 'admin@example.com', 'adminpass', 'Admin'),
('viewer', 'viewer@example.com', 'viewerpass', 'Viewer');

-- Insert initial platform data with a default progress stage
INSERT INTO platforms (name, status, image_url, grafana_url, manage_type, manage_url, progress_stage) VALUES
('Ayla', 'Online', 'https://placehold.co/100x100/A0E7E5/000000?text=Ayla', 'https://grafana.example.com/d/ayla', 'ssh', 'ssh://user@ayla.example.com', 'RFP'),
('SAH', 'Offline', 'https://placehold.co/100x100/F9D0A7/000000?text=SAH', 'https://grafana.example.com/d/sah', 'ssh', 'ssh://user@sah.example.com', 'CRC'),
('CIOT', 'Online', 'https://placehold.co/100x100/C4D1FF/000000?text=CIOT', 'https://grafana.example.com/d/ciot', 'ssh', 'ssh://user@ciot.example.com', 'ATP'),
('AI', 'Online', 'https://placehold.co/100x100/FFD6A5/000000?text=AI', 'https://grafana.example.com/d/ai', 'ssh', 'ssh://user@ai.example.com', 'POC'),
('SAQR', 'Online', 'https://placehold.co/100x100/A2E3B9/000000?text=SAQR', 'https://grafana.example.com/d/saqr', 'ssh', 'ssh://user@saqr.example.com', 'RFS');

