import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import PageTransition from "@/components/PageTransition";

const NotFound = () => {
  return (
    <PageTransition>
      <div className="min-h-screen flex items-center justify-center bg-background relative overflow-hidden">
        {/* Background Effects */}
        <div className="absolute inset-0 bg-gradient-hero" />
        <div className="absolute top-1/3 left-1/3 w-96 h-96 bg-primary/10 rounded-full blur-3xl animate-pulse-glow" />
        
        <div className="text-center space-y-6 relative z-10 px-4">
          <h1 className="text-8xl sm:text-9xl font-bold font-display text-gradient">404</h1>
          <h2 className="text-2xl sm:text-3xl font-bold font-display">Page Not Found</h2>
          <p className="text-muted-foreground max-w-md mx-auto">
            The page you're looking for doesn't exist or has been moved.
          </p>
          <Button variant="primary" size="lg" asChild>
            <Link to="/">Back to Home</Link>
          </Button>
        </div>
      </div>
    </PageTransition>
  );
};

export default NotFound;
